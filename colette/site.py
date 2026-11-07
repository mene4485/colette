"""Site visé par Colette : le vrai Free Mobile, ou la maquette (clone) avec un compte fictif.

    COLETTE_SITE=free   (défaut)  https://mobile.free.fr/account/ · skills colette/skills/
    COLETTE_SITE=demo             maquette (colette/demo_site.py) · skills colette/skills_demo/
    COLETTE_SITE_URL=...          URL de l'espace abonné de la maquette (défaut http://localhost:8000/account/,
                                  en ligne : https://<projet>.vercel.app/account/)

Connexion : la personne tape TOUJOURS elle-même ses identifiants. En mode en ligne (agent dans un
navigateur cloud), elle se connecte sur sa propre page et la bulle partage la session avec l'agent
(jeton /colette/handoff → l'agent ouvre /colette/claim?t=…).
"""

from __future__ import annotations

import os
from pathlib import Path

HERE = Path(__file__).parent

FREE_URL = "https://mobile.free.fr/account/"
DEMO_URL = "http://localhost:8000/account/"
DEMO_LOGIN = "12345678"
DEMO_PASSWORD = "colette"

FREE_LOGIN = (
    "If a login page appears, call ask_user with exactly this question: \"You need to log in. Type\n"
    "your ID and your password yourself, I'm not looking. Tell me 'done' when you're finished.\" NEVER\n"
    "ask for the ID, the password or a code: the person types them herself. Wait for her answer\n"
    "before continuing."
)

DEMO_LOGIN_TEXT = (
    FREE_LOGIN + "\n"
    "If her answer contains an address starting with http, open exactly that address in the address\n"
    "bar: it logs you in with the session the person just opened. Do not type any ID or password.\n"
    "If a cookie banner appears, click \"Continue without accepting\"."
)


def name() -> str:
    return (os.getenv("COLETTE_SITE") or "free").strip().lower()


def is_demo() -> bool:
    return name() == "demo"


def start_url() -> str:
    if is_demo():
        return (os.getenv("COLETTE_SITE_URL") or DEMO_URL).strip()
    return FREE_URL


def site_label() -> str:
    return "Free Mobile customer area, demo mock-up" if is_demo() else "Free Mobile customer area"


def login_instructions() -> str:
    return DEMO_LOGIN_TEXT if is_demo() else FREE_LOGIN


def skills_dir() -> Path:
    return HERE / ("skills_demo" if is_demo() else "skills")
