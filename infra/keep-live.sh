#!/bin/bash
# Watchdog ComplexSim API: mantém uvicorn + túnel cloudflared vivos e
# publica a URL pública atual em docs/LIVE_URL.md (commit+push automático).
# Uso: nohup ./infra/keep-live.sh >/tmp/complexsim-keep.log 2>&1 &
cd "$(dirname "$0")/.." || exit 1
API_LOG=/tmp/complexsim-api.log
TUN_LOG=/tmp/complexsim-tunnel.log
URL_FILE=docs/LIVE_URL.md

start_api() {
  pgrep -f "uvicorn app.main:app" >/dev/null || {
    echo "[keep] iniciando API..."
    (cd backend && nohup python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >"$API_LOG" 2>&1 &)
    sleep 5
  }
}

start_tunnel() {
  pgrep -f "cloudflared tunnel" >/dev/null || {
    echo "[keep] iniciando túnel..."
    : >"$TUN_LOG"
    nohup cloudflared tunnel --url http://127.0.0.1:8000 >"$TUN_LOG" 2>&1 &
    sleep 10
  }
}

publish_url() {
  local url
  url=$(grep -aoE "https://[a-z0-9-]+\.trycloudflare\.com" "$TUN_LOG" 2>/dev/null | head -n 1)
  [ -z "$url" ] && return 0
  local cur
  cur=$(grep -aoE "https://[a-z0-9-]+\.trycloudflare\.com" "$URL_FILE" 2>/dev/null | head -n 1)
  if [ "$url" != "$cur" ]; then
    echo "[keep] nova URL pública: $url"
    cat >"$URL_FILE" <<EOF
# ComplexSim — API pública (túnel temporário)

- **URL atual:** $url
- **Docs:** $url/docs
- **Atualizado em:** $(date -u +%Y-%m-%dT%H:%M:%SZ)
- **Uso no frontend:** \`?api=$url\`

> Túnel quick do Cloudflare: a URL muda a cada reinício e morre com o
> processo. Para URL fixa, use \`render.yaml\` (1 clique no dashboard Render).
EOF
    git add "$URL_FILE" >/dev/null 2>&1
    git -c user.name="orquestrador" -c user.email="orc@local" commit -qm "live: atualiza URL pública da API" >/dev/null 2>&1
    git push origin master >/dev/null 2>&1
  fi
}

while true; do
  start_api
  if curl -s --max-time 8 http://127.0.0.1:8000/health >/dev/null 2>&1; then
    start_tunnel
    publish_url
  else
    echo "[keep] API fora do ar; tentando reiniciar..."
    pkill -f "uvicorn app.main:app"
    sleep 2
  fi
  sleep 45
done
