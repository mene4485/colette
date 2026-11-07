"""Site visé par Colette : le vrai Free Mobile, ou la maquette (clone) avec un compte fictif.

    COLETTE_SITE=free   (défaut)  https://mobile.free.fr/account/ · skills colette/skills/
    COLETTE_SITE=demo             maquette (colette/demo_site.py) · skills colette/skills_demo/
    COLETTE_SITE_URL=...          URL de l'espace abonné de la maquette (défaut http://localhost:8000/account/,
                                  en ligne : https://<projet>.vercel.app/account/)

Sur la maquette, le compte est fictif : l'agent H tape lui-même l'identifiant et le mot de passe de
démo (en mode hébergé, la personne ne voit le navigateur de l'agent qu'en direct, sans pouvoir taper).
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
    "Si une page de connexion apparaît : tu ne connais PAS les identifiants de la personne, demande-les-lui.\n"
    "1. Appelle ask_user avec exactement : « Pour vous connecter, quel est votre identifiant Free ? Ce sont 8 chiffres. »\n"
    "   Tape dans le champ « Identifiant » seulement les chiffres de sa réponse (« un deux trois » → 123, sans espaces).\n"
    "2. Appelle ask_user avec exactement : « Et quel est votre mot de passe ? »\n"
    "   Tape sa réponse dans le champ « Mot de passe », sans point final ni espace (un seul mot dit à voix haute :\n"
    "   écris-le en minuscules).\n"
    "3. Clique « Se connecter ». Si la page dit « Identifiant ou mot de passe incorrect », redemande seulement\n"
    "   l'information qui semble fausse, une seule fois, puis réessaie.\n"
    "N'invente jamais d'identifiant ni de mot de passe. Ne les répète pas dans tes messages.\n"
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
