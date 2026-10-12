# Derechos On — imagen para publicar el panel en un hosting de contenedores
# (Render, Koyeb, Railway, Fly.io, etc.) SIN VPS.
#
# Build local:  docker build -t derechos-on .
# Run local:    docker run -p 8000:8000 -e SECRET_KEY=cambia-esto derechos-on

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p uploads && touch derechos.db

EXPOSE 8000

# Un solo worker + hilos: mantiene la BD SQLite y evita duplicar el
# registro automático de redes. Ajusta workers si usas un disco persistente.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 8 --timeout 120 wsgi:application"]
