FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Roda sem root (Task 7.1): uma falha na app nao vira root no container.
RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app

EXPOSE 8000

# Processos de API por container; para escalar mais, suba mais replicas.
ENV WEB_CONCURRENCY=2

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

# --proxy-headers: atras de proxy/balanceador, loga o IP real do cliente.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' --workers ${WEB_CONCURRENCY}"]
