# syntax=docker/dockerfile:1
#
# Dockerfile – Grana Backend (FastAPI)
#
# Zweistufiger Build:
#   1. builder  – installiert Python-Abhängigkeiten (inkl. Build-Tools, falls
#                 für eine Zielarchitektur ausnahmsweise aus dem Quellcode
#                 kompiliert werden muss -- landet NICHT im finalen Image).
#   2. runtime  – schlankes Image, läuft als Non-Root-User.
#
# Hinweis opencv-python-headless: das Wheel bringt seine Laufzeitbibliotheken
# (ffmpeg, libpng, openblas, ...) bereits mitgeliefert -- verifiziert per
# `ldd` gegen das installierte Wheel; keine zusätzlichen apt-Pakete (libgl1,
# libglib2.0-0 o.ä.) nötig.

# ============================================================================
# Stage 1: builder
# ============================================================================
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================================================================
# Stage 2: runtime
# ============================================================================
FROM python:3.11-slim AS runtime

WORKDIR /app

RUN groupadd --system grana && useradd --system --gid grana --create-home grana

COPY --from=builder /install /usr/local

COPY . .

# data/card_images wird zur Laufzeit vom Local-Matcher (services/local_matcher.py)
# befüllt -- Verzeichnis muss existieren und dem Non-Root-User gehören.
RUN mkdir -p /app/data/card_images \
    && chown -R grana:grana /app

USER grana

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8001

EXPOSE 8001

# $PORT folgt der Konvention von Railway/Heroku & Co. (wird von der Plattform
# gesetzt); lokal ohne gesetzte Variable Default 8001 aus ENV oben.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8001\")}/health', timeout=3)" || exit 1

# --proxy-headers: sonst ist die Gegenstelle hinter einem Reverse-Proxy
# immer der Proxy, und alle Nutzer teilen sich ein Drosselungs-Kontingent.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT} \
    --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-*}"
