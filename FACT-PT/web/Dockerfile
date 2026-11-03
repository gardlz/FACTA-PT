# The interface: React + Vite, built to static files that FastAPI serves.
FROM node:24-alpine AS interface

WORKDIR /web/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
# Writes to /web/app/static (see `build.outDir` in vite.config.js).
RUN npm run build


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

RUN adduser --system --group --no-create-home aplicacao

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY --from=interface /web/app/static ./app/static

# Where the runs are kept: a volume shared with the worker mounts here, and takes this ownership.
RUN mkdir -p /dados/execucoes && chown -R aplicacao:aplicacao /srv /dados
USER aplicacao

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/sessao', timeout=4).status==200 else 1)"

ENV WEB_WORKERS=2
# The proxies whose X-Forwarded-For names the client (addresses or networks, comma-separated),
# read by uvicorn itself. Anyone else's is ignored: trusted from everyone, a client could pick
# its own address and get round the sign-in throttle and RUNS_PER_ADDRESS.
ENV FORWARDED_ALLOW_IPS=127.0.0.1,::1

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_WORKERS} --proxy-headers"]
