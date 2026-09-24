FROM python:3.12-slim

# Dépendances système : compilation de mysqlclient (CDC 5.1) + Pillow (libjpeg/zlib)
# + cron pour les tâches planifiées (CDC 5.6, 5.2 : « Tâches cron »).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        default-libmysqlclient-dev \
        pkg-config \
        libjpeg62-turbo-dev \
        zlib1g-dev \
        cron \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Daphne sert HTTP et WebSocket (5.1, 5.5). Migrations et collectstatic sont
# lancés par le script d'entrée, jamais dans l'image (5.11).
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
COPY docker-entrypoint-cron.sh /app/docker-entrypoint-cron.sh
RUN sed -i 's/\r$//' /app/docker-entrypoint.sh /app/docker-entrypoint-cron.sh \
    && chmod +x /app/docker-entrypoint.sh /app/docker-entrypoint-cron.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "backend.asgi:application"]
