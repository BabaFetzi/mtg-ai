#!/usr/bin/env bash
# ============================================================================
# start.sh – Produktions-Start für Grana (MTG-AI)
#
# Fährt das Projekt in dieser Reihenfolge hoch:
#   1. Prüft/lädt die .env
#   2. Startet die Infra-Container Postgres + Redis (docker-compose.infra.yml)
#      und wartet, bis beide "healthy" sind
#   3. Baut das Frontend zu statischen Dateien (mtg-frontend/dist)
#   4. Startet das FastAPI-Backend (uvicorn) im Vordergrund
#
# Das Backend läuft NATIV (kein App-Container); nur DB & Redis sind Container.
# Das gebaute Frontend (mtg-frontend/dist) wird von DEINEM Reverse-Proxy
# (nginx/Caddy) ausgeliefert -- dieser muss außerdem /api an das Backend
# weiterreichen (siehe Hinweise am Ende der Ausgabe).
#
# Aufruf:
#   ./start.sh                # alles: Infra + Frontend-Build + Backend
#   ./start.sh --skip-build   # Frontend NICHT neu bauen (nur Infra + Backend)
#   ./start.sh --infra-only   # nur Postgres + Redis starten, dann beenden
#   ./start.sh --no-infra     # Infra-Container nicht anfassen (extern verwaltet)
#   ./start.sh --stop         # Backend-Prozess läuft im Vordergrund; dies
#                             #   stoppt die Infra-Container
#
# Wird das Skript mit Strg+C beendet, stoppt nur das Backend; die Infra-
# Container laufen absichtlich weiter (Daten bleiben erhalten). Zum Stoppen
# der Container:  ./start.sh --stop
# ============================================================================

set -euo pipefail

# ----------------------------------------------------------------------------
# In das Verzeichnis dieses Skripts wechseln (Projektwurzel)
# ----------------------------------------------------------------------------
cd "$(dirname "$(readlink -f "$0")")"

# --- Farben für Log-Ausgaben --------------------------------------------------
if [ -t 1 ]; then
  C_INFO='\033[1;34m'; C_OK='\033[1;32m'; C_WARN='\033[1;33m'; C_ERR='\033[1;31m'; C_OFF='\033[0m'
else
  C_INFO=''; C_OK=''; C_WARN=''; C_ERR=''; C_OFF=''
fi
info() { echo -e "${C_INFO}[start]${C_OFF} $*"; }
ok()   { echo -e "${C_OK}[start]${C_OFF} $*"; }
warn() { echo -e "${C_WARN}[start]${C_OFF} $*"; }
die()  { echo -e "${C_ERR}[start] FEHLER:${C_OFF} $*" >&2; exit 1; }

# ----------------------------------------------------------------------------
# Argumente parsen
# ----------------------------------------------------------------------------
SKIP_BUILD=0
INFRA_ONLY=0
NO_INFRA=0
DO_STOP=0
for arg in "$@"; do
  case "$arg" in
    --skip-build) SKIP_BUILD=1 ;;
    --infra-only) INFRA_ONLY=1 ;;
    --no-infra)   NO_INFRA=1 ;;
    --stop)       DO_STOP=1 ;;
    -h|--help)
      sed -n '2,40p' "$0"; exit 0 ;;
    *) die "Unbekanntes Argument: $arg (siehe --help)" ;;
  esac
done

# ----------------------------------------------------------------------------
# docker compose Wrapper (v2 "docker compose" bevorzugt, sonst "docker-compose")
# ----------------------------------------------------------------------------
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  DC=""
fi
COMPOSE_FILE="docker-compose.infra.yml"

# ----------------------------------------------------------------------------
# --stop: Infra-Container herunterfahren und raus
# ----------------------------------------------------------------------------
if [ "$DO_STOP" -eq 1 ]; then
  [ -n "$DC" ] || die "docker compose nicht gefunden."
  info "Stoppe Infra-Container (Daten in Volumes bleiben erhalten)..."
  $DC -f "$COMPOSE_FILE" down
  ok "Infra-Container gestoppt."
  exit 0
fi

# ----------------------------------------------------------------------------
# 1) .env prüfen und laden
# ----------------------------------------------------------------------------
[ -f .env ] || die ".env nicht gefunden. Vorlage kopieren:  cp .env.production.example .env  und ausfüllen."

info "Lade .env ..."
set -a
# shellcheck disable=SC1091
source .env
set +a

# Pflicht-Variablen für einen sauberen Prod-Start prüfen
REQUIRED=(DATABASE_URL REDIS_URL JWT_SECRET_KEY ALLOWED_ORIGINS)
MISSING=()
for v in "${REQUIRED[@]}"; do
  [ -n "${!v:-}" ] || MISSING+=("$v")
done
if [ "${#MISSING[@]}" -gt 0 ]; then
  die "Fehlende Pflicht-Variablen in .env: ${MISSING[*]}"
fi

# Weiche Warnungen für Zahlungen/KI (App startet trotzdem)
for v in STRIPE_SECRET_KEY STRIPE_WEBHOOK_SECRET STRIPE_PRICE_ID GEMINI_API_KEY; do
  [ -n "${!v:-}" ] || warn "$v ist nicht gesetzt -- zugehörige Funktion ist deaktiviert."
done

case "${DATABASE_URL:-}" in
  sqlite*) warn "DATABASE_URL zeigt auf SQLite -- für Produktion PostgreSQL verwenden!" ;;
esac

# ----------------------------------------------------------------------------
# 2) Infra-Container (Postgres + Redis) starten und auf "healthy" warten
# ----------------------------------------------------------------------------
if [ "$NO_INFRA" -eq 0 ]; then
  [ -n "$DC" ] || die "docker compose nicht gefunden. Docker installieren oder mit --no-infra starten."
  [ -n "${POSTGRES_PASSWORD:-}" ] || die "POSTGRES_PASSWORD ist in .env nicht gesetzt (von Postgres-Container benötigt)."

  info "Starte Infra-Container (Postgres + Redis) ..."
  $DC -f "$COMPOSE_FILE" up -d

  info "Warte, bis Postgres + Redis 'healthy' sind ..."
  for svc in postgres redis; do
    cid="$($DC -f "$COMPOSE_FILE" ps -q "$svc")"
    [ -n "$cid" ] || die "Container '$svc' wurde nicht gestartet."
    for i in $(seq 1 30); do
      status="$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo unknown)"
      if [ "$status" = "healthy" ]; then
        ok "$svc ist healthy."
        break
      fi
      [ "$i" -eq 30 ] && die "$svc wurde nicht rechtzeitig healthy (Status: $status). Logs: $DC -f $COMPOSE_FILE logs $svc"
      sleep 2
    done
  done
else
  info "--no-infra: überspringe Postgres/Redis (extern verwaltet)."
fi

if [ "$INFRA_ONLY" -eq 1 ]; then
  ok "--infra-only: Infra läuft. Fertig."
  exit 0
fi

# ----------------------------------------------------------------------------
# 3) Frontend bauen (statische Dateien nach mtg-frontend/dist)
# ----------------------------------------------------------------------------
if [ "$SKIP_BUILD" -eq 0 ]; then
  command -v npm >/dev/null 2>&1 || die "npm nicht gefunden (Node.js benötigt), oder mit --skip-build starten."
  info "Baue Frontend (npm ci && npm run build) ..."
  (
    cd mtg-frontend
    if [ -f package-lock.json ]; then
      npm ci
    else
      npm install
    fi
    npm run build
  )
  ok "Frontend gebaut -> mtg-frontend/dist"
else
  info "--skip-build: überspringe Frontend-Build."
fi

# ----------------------------------------------------------------------------
# 4) Backend-Abhängigkeiten sicherstellen (venv) und uvicorn starten
# ----------------------------------------------------------------------------
if [ ! -d .venv ]; then
  info "Erzeuge Python-venv (.venv) ..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

info "Installiere/aktualisiere Backend-Abhängigkeiten ..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

PORT="${PORT:-8001}"
WORKERS="${UVICORN_WORKERS:-2}"

ok "Starte Backend (uvicorn) auf 0.0.0.0:${PORT} mit ${WORKERS} Worker(n) ..."
echo
info "Nächste Schritte (einmalig einzurichten):"
echo    "  * Reverse-Proxy (nginx/Caddy) so konfigurieren, dass er"
echo    "      - die statischen Dateien aus  mtg-frontend/dist  ausliefert"
echo    "      - Anfragen an  /api  auf  http://127.0.0.1:${PORT}  weiterreicht (inkl. WebSocket /api/vision/stream)"
echo    "  * TLS am Reverse-Proxy terminieren; ALLOWED_ORIGINS/FRONTEND_URL müssen zur echten Domain passen."
echo    "  * Migration bestehender SQLite-Daten nach Postgres (einmalig):  python migrate_sqlite_to_postgres.py"
echo
# --proxy-headers: hinter einem Reverse-Proxy ist die Gegenstelle sonst immer
# der Proxy selbst. Alle Nutzer sähen damit für Drosselung und Protokoll wie
# EIN Besucher aus. FORWARDED_ALLOW_IPS sagt, welchem Proxy dabei geglaubt wird
# -- standardmässig nur dem auf demselben Rechner.
FORWARDED="${FORWARDED_ALLOW_IPS:-127.0.0.1}"

# exec -> uvicorn ersetzt die Shell, damit Signale (systemd/Strg+C) sauber ankommen.
exec uvicorn main:app --host 0.0.0.0 --port "${PORT}" --workers "${WORKERS}" \
     --proxy-headers --forwarded-allow-ips "${FORWARDED}" --no-access-log
