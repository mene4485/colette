#!/usr/bin/env bash
# Teste le mode en ligne sur le laptop : maquette (comme sur Vercel) :8013 + backend :8080.
#   scripts/run_hosted_local.sh          # vrai agent H en navigateur cloud (il faut une URL publique de la maquette !)
#   COLETTE_FAKE=1 scripts/run_hosted_local.sh   # faux agent H
# Puis ouvrir http://localhost:8013/account/ et cliquer « Parler à Colette ».
set -euo pipefail
cd "$(dirname "$0")/.."
export COLETTE_BACKEND_URL="${COLETTE_BACKEND_URL:-http://localhost:8080}"
export COLETTE_SITE_URL="${COLETTE_SITE_URL:-http://localhost:8013/account/}"
.venv/bin/python -c "
import http.server, sys; sys.path.insert(0, '.')
from colette.demo_site import CloudHandler
http.server.ThreadingHTTPServer(('127.0.0.1', 8013), CloudHandler).serve_forever()" &
SITE=$!
trap 'kill $SITE' EXIT
.venv/bin/uvicorn colette.hosted:app --host 127.0.0.1 --port 8080
