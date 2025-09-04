# 🌸 SSH Journal — AI-Powered Journaling over SSH 🌸

Welcome to **SSH Journal** — a minimalist, terminal-first journaling app for devs!! 
you can log into via SSH.  
It’s like keeping a secret diary on a remote machine… except this one can **ask you questions** and **help generate tomorrow’s prompts with AI** ✨

```
===========================================================
       __        __   _                           
       \ \      / /__| | ___ ___  _ __ ___   ___  
        \ \ /\ / / _ \ |/ __/ _ \| '_ ` _ \ / _ \ 
         \ V  V /  __/ | (_| (_) | | | | | |  __/ 
          \_/\_/ \___|_|\___\___/|_| |_| |_|\___|    

                🌸  WELCOME TO SSH-JOURNAL 🌸
===========================================================
```
---

## 🐚 Features

- 🔑 **SSH-based login** — just `ssh -p 2222 localhost` to start journaling
- 🪪 **Identity by SSH key fingerprint** — no clunky passwords
- 📖 **Daily journaling prompts** — generated with GPT-4o-mini
- 🕰 **Auto-saved entries** — stored safely in PostgreSQL
- ⏮ **History & review** — view or edit past entries
- 🎨 **Cute terminal UI** — ASCII banners & prompts
- 🌐 **LAN-accessible** — run on your laptop, connect from anywhere on your Wi-Fi

---

## ✨ Quick Start

1. **Clone & install deps**
   ```bash
   git clone https://github.com/yourname/ssh-journal.git
   cd ssh-journal
   pip install -r requirements.txt
