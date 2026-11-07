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
    "Si une page de connexion apparaît, appelle ask_user avec exactement cette question : « Il faut\n"
    "vous connecter. Tapez vous-même votre identifiant et votre mot de passe, je ne regarde pas.\n"
    "Dites-moi « c'est bon » quand c'est fait. » Ne demande JAMAIS l'identifiant, le mot de passe ni\n"
    "un code : la personne les tape elle-même. Attends sa réponse avant de continuer."
)

DEMO_LOGIN_TEXT = (
    FREE_LOGIN + "\n"
    "Si sa réponse contient une adresse qui commence par http, ouvre exactement cette adresse dans la\n"
    "barre d'adresse : elle te connecte avec la session que la personne vient d'ouvrir. Ne tape aucun\n"
    "identifiant ni mot de passe.\n"
    "Si un bandeau de cookies apparaît, clique « Continuer sans accepter »."
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
    return "espace abonné Free Mobile, maquette de démonstration" if is_demo() else "espace abonné Free Mobile"


def login_instructions() -> str:
    return DEMO_LOGIN_TEXT if is_demo() else FREE_LOGIN


def skills_dir() -> Path:
    return HERE / ("skills_demo" if is_demo() else "skills")
