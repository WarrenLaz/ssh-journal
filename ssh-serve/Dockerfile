FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates openssh-client && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN pip install --no-cache-dir asyncssh==2.14.2 psycopg2-binary==2.9.9 python-dotenv==1.0.1

COPY app.py /app/app.py

RUN useradd -m journal && chown -R journal:journal /app
USER journal

EXPOSE 2222
CMD ["python", "/app/app.py"]
