FROM python:3.11-slim

# Minimal OS deps for psycopg2-binary & OpenSSL
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates openssh-client && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
RUN pip install --no-cache-dir asyncssh==2.14.2 psycopg2-binary==2.9.9 python-dotenv==1.0.1

# Copy app & host key at runtime via volume (compose mounts them)
COPY app.py /app/app.py

# Non-root user
RUN useradd -m journal && chown -R journal:journal /app
USER journal

EXPOSE 2222
CMD ["python", "/app/app.py"]
