"""Point d'entrée Vercel (runtime Python) : la maquette Free Mobile, état du compte en cookie signé.

Variables Vercel : COLETTE_BACKEND_URL (wss://… du backend voix + agent, optionnel),
COLETTE_DEMO_SECRET (signature des cookies).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from colette.demo_site import CloudHandler  # noqa: E402


class handler(CloudHandler):  # noqa: N801  (nom imposé par Vercel)
    cookie_banner = True
