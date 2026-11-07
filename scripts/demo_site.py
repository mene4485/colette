"""Lance seule la maquette de l'espace abonné Free Mobile (compte fictif) sur http://localhost:8000.

    .venv\\Scripts\\python scripts\\demo_site.py              (Windows)
    .venv/bin/python scripts/demo_site.py                  (macOS)
Options : --port 8000, --reset (remet le compte à zéro), --no-cookie-banner.
Compte de démo : identifiant 12345678, mot de passe colette.

Avec Colette, plus simple : scripts/run_colette.py --demo-site (lance la maquette en même temps).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from colette.demo_site import DEFAULT_PORT, DEMO_LOGIN, DEMO_PASSWORD, Store, make_server  # noqa: E402
from colette.platform_compat import setup_console  # noqa: E402


def main() -> None:
    setup_console()
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--reset", action="store_true", help="remet le compte de démo à zéro")
    p.add_argument("--no-cookie-banner", action="store_true")
    args = p.parse_args()
    store = Store()
    if args.reset:
        store.reset()
        print("Compte de démo réinitialisé.")
    server = make_server(args.port, cookie_banner=not args.no_cookie_banner, store=store)
    print(f"Maquette Free Mobile : http://localhost:{args.port}/account/")
    print(f"Compte de démo : identifiant {DEMO_LOGIN} · mot de passe {DEMO_PASSWORD}")
    print("Ctrl+C pour arrêter.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
