import asyncio, asyncssh, os, sys, textwrap, datetime as dt
import psycopg2, psycopg2.extras
from psycopg2.extras import RealDictCursor
from base64 import b64encode
from hashlib import sha256
from dotenv import load_dotenv

load_dotenv()
# ---- Config from env ----
DB_DSN = os.getenv("DB_DSN")
TZ = os.getenv("APP_TZ", "America/Detroit")     # your default “journal day” zone
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ---- DB helpers ----
def db():
    return psycopg2.connect(DB_DSN, cursor_factory=RealDictCursor)

def ensure_schema():
    with db() as conn, conn.cursor() as cur:
        cur.execute("""
        create extension if not exists pgcrypto;
        create table if not exists users(
          id uuid primary key default gen_random_uuid(),
          fingerprint text unique not null,
          handle text,
          created_at timestamptz not null default now()
        );
        create table if not exists journal_entries(
          id uuid primary key default gen_random_uuid(),
          user_id uuid references users(id) on delete cascade,
          entry_date date not null,
          body text not null,
          created_at timestamptz not null default now(),
          constraint uniq_user_day unique(user_id, entry_date)
        );
        create table if not exists daily_questions(
          id uuid primary key default gen_random_uuid(),
          user_id uuid references users(id) on delete cascade,
          for_date date not null,
          question text not null,
          created_at timestamptz not null default now(),
          constraint uniq_q_user_day unique(user_id, for_date)
        );
        """)
    print("DB ready.", file=sys.stderr)

def key_fingerprint(pubkey: asyncssh.SSHKey) -> str:
    # SSH-style SHA256 fingerprint
    raw = pubkey.export_public_key(format_name='ssh').encode()
    # Normalize to the key bytes (skip 'ssh-ed25519 ' prefix)
    key_blob = raw.split(None, 2)[1]
    decoded = asyncssh.base64.decode(key_blob)
    fp = b"SHA256:" + b64encode(sha256(decoded).digest()).rstrip(b'=')
    return fp.decode()

def get_or_create_user(fp: str):
    with db() as conn, conn.cursor() as cur:
        cur.execute("select * from users where fingerprint=%s", (fp,))
        row = cur.fetchone()
        if row: return row
        cur.execute("insert into users(fingerprint) values(%s) returning *", (fp,))
        return cur.fetchone()

def today_local_date() -> dt.date:
    # journal "day" uses wall time in TZ. Keep simple: convert from UTC offset.
    # For production, use pytz/zoneinfo to handle DST properly.
    try:
        from zoneinfo import ZoneInfo
        now = dt.datetime.now(ZoneInfo(TZ))
    except Exception:
        now = dt.datetime.utcnow()
    return now.date()

def get_question(user_id, for_date):
    with db() as conn, conn.cursor() as cur:
        cur.execute("select question from daily_questions where user_id=%s and for_date=%s",
                    (user_id, for_date))
        row = cur.fetchone()
        if row: return row["question"]
    return "How are you feeling today?"

def set_question(user_id, for_date, q):
    with db() as conn, conn.cursor() as cur:
        cur.execute("""
            insert into daily_questions(user_id, for_date, question)
            values(%s,%s,%s)
            on conflict (user_id, for_date) do update set question=excluded.question
        """, (user_id, for_date, q))

def get_yesterdays_entry(user_id, day):
    yday = day - dt.timedelta(days=1)
    with db() as conn, conn.cursor() as cur:
        cur.execute("select body from journal_entries where user_id=%s and entry_date=%s",
                    (user_id, yday))
        row = cur.fetchone()
        return (yday, row["body"]) if row else (yday, "")

def get_today_entry(user_id, day):
    with db() as conn, conn.cursor() as cur:
        cur.execute("select * from journal_entries where user_id=%s and entry_date=%s",
                    (user_id, day))
        return cur.fetchone()

def save_entry(user_id, day, body):
    with db() as conn, conn.cursor() as cur:
        cur.execute("""
          insert into journal_entries(user_id, entry_date, body)
          values(%s,%s,%s)
          on conflict (user_id, entry_date) do update set body=excluded.body
          returning id
        """, (user_id, day, body))
        return cur.fetchone()["id"]

async def gen_tomorrow_question(yesterday_text: str) -> str:
    if not OPENAI_API_KEY or not yesterday_text.strip():
        return "What do you want to explore tomorrow?"
    # Minimal OpenAI Chat Completions call via requests (no external deps)
    import json, urllib.request
    prompt_sys = "You are a supportive daily journaling coach. Ask exactly ONE concise open-ended question (max 140 characters) that builds on the user's prior entry."
    prompt_user = f'Yesterday:\n"""\n{yesterday_text[:4000]}\n"""'
    data = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role":"system","content":prompt_sys},
            {"role":"user","content":prompt_user}
        ],
        "max_tokens": 80,
        "temperature": 0.7
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(data).encode(),
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}",
                 "Content-Type":"application/json"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        out = json.loads(resp.read())
        q = out["choices"][0]["message"]["content"].strip()
        return q.splitlines()[0][:140]

WELCOME = """\
╭──────────────────────────────────────────────╮
│  SSH Journal                                │
│  Commands: :edit  :history  :view YYYY-MM-DD│
│            :quit                            │
╰──────────────────────────────────────────────╯
"""

async def handle_session(sess: asyncssh.SSHServerSession):
    s = sess
    pub = s.get_extra_info('public_key')
    if not pub:
        s.write("Public-key auth required.\n"); s.exit(1); return
    fp = key_fingerprint(pub)
    user = get_or_create_user(fp)
    uid = user["id"]

    today = today_local_date()
    q = get_question(uid, today)

    s.write(WELCOME + f"\nHello. Your key: {fp}\n\n")
    s.write(f"Today is {today.isoformat()}\n")
    s.write(f"Question: {q}\n\n")

    # load existing body if any
    existing = get_today_entry(uid, today)
    body = existing["body"] if existing else ""

    s.write("Type your entry below. End with a line containing only '::save'\n")
    s.write("(or type :edit / :history / :view YYYY-MM-DD / :quit)\n\n")

    buf = []
    if body:
        s.write("(You already have an entry; :edit to modify or :history to view.)\n")

    while True:
        s.write("> ")
        line = (await s.stdin.readline())
        if not line:
            break
        line = line.rstrip("\n")

        if line == ":quit":
            s.write("Bye.\n"); break

        if line == ":history":
            # show last 7 days
            with db() as conn, conn.cursor() as cur:
                cur.execute("""
                    select entry_date, left(body,80)||case when length(body)>80 then '…' else '' end as preview
                    from journal_entries
                    where user_id=%s
                    order by entry_date desc limit 7
                """, (uid,))
                rows = cur.fetchall()
                if not rows:
                    s.write("No history yet.\n")
                else:
                    s.write("\nRecent entries:\n")
                    for r in rows:
                        s.write(f"  {r['entry_date']}: {r['preview']}\n")
                continue

        if line.startswith(":view "):
            try:
                d = dt.date.fromisoformat(line.split()[1])
            except Exception:
                s.write("Usage: :view YYYY-MM-DD\n"); continue
            with db() as conn, conn.cursor() as cur:
                cur.execute("select body from journal_entries where user_id=%s and entry_date=%s",
                            (uid, d))
                row = cur.fetchone()
                if not row:
                    s.write("No entry for that date.\n")
                else:
                    s.write("\n" + "-"*50 + f"\n{d}\n" + "-"*50 + "\n")
                    s.write(row["body"] + "\n")
                    s.write("-"*50 + "\n")
            continue

        if line == ":edit":
            s.write("Editing today. Finish with '::save' on its own line.\n")
            buf = []
            continue

        if line == "::save":
            final = "\n".join(buf).strip()
            if not final:
                s.write("Nothing to save.\n"); continue
            save_entry(uid, today, final)
            s.write("Saved.\n")
            # generate tomorrow's question using today's text
            tomorrow = today + dt.timedelta(days=1)
            q2 = await gen_tomorrow_question(final)
            set_question(uid, tomorrow, q2)
            s.write(f"Queued tomorrow’s question: {q2}\n")
            buf = []
            continue

        # default: accumulate into buffer
        buf.append(line)

class Server(asyncssh.SSHServer):
    def connection_made(self, conn): pass
    def connection_lost(self, exc): pass

async def start():
    ensure_schema()
    # Host key (create once: ssh-keygen -t ed25519 -f ./host_ed25519 -N '')
    host_key = os.getenv("HOST_KEY_PATH", "./host_ed25519")
    await asyncssh.create_server(
        lambda: Server(),
        '', 2222,
        server_host_keys=[host_key],
        authorized_client_keys=None,    # we'll accept any key in the session handler
        session_factory=handle_session
    )
    await asyncio.Future()

if __name__ == '__main__':
    try:
        asyncio.run(start())
    except (OSError, asyncssh.Error) as exc:
        print(f'Error starting server: {exc}', file=sys.stderr)
        sys.exit(1)
