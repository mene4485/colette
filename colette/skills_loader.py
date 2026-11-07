"""Charge `colette/skills/*.md` en skills H inline `{name, description, body}`.

Chaque fichier commence par un front matter :

    ---
    name: free-plan
    description: Use when …
    ---
    # Corps markdown (la procédure)

Aucune liste en dur : tout fichier `.md` déposé dans le dossier est envoyé à l'agent.
"""

from __future__ import annotations

import re
from pathlib import Path

from loguru import logger

SKILLS_DIR = Path(__file__).parent / "skills"
# Ajouté en tête de chaque skill : Holo suit le corps du skill bien plus que les instructions
# générales (vu au vrai run du 7 nov : skill suivi à la lettre, annoncer_etapes jamais appelé).
PREAMBLE = """\
## Before anything else (Colette)
1. Call `annoncer_etapes` FIRST, before any action on the website: 3 to 6 short steps in simple
   French that follow this skill (e.g. « Ouvrir votre espace abonné », « Trouver vos factures »).
   If something will need to be validated, the last step is exactly « Valider avec votre accord ».
2. After finishing each of those steps, call `etape_terminee` with its number (starting at 1).
3. Before any click that validates, saves, pays or cancels, call `confirm_change` and click only
   if the reply starts with "Approved".
"""
_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def parse_skill(text: str, fallback_name: str) -> dict:
    """Front matter `name` / `description` + corps. Lève ValueError si incomplet."""
    meta: dict[str, str] = {}
    body = text
    if text.startswith("---"):
        _, front, body = text.split("---", 2)
        for line in front.strip().splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                meta[key.strip().lower()] = value.strip().strip("\"'")
    name = meta.get("name") or fallback_name
    description = meta.get("description", "")
    body = body.strip()
    if not _NAME_RE.match(name):
        raise ValueError(f"nom de skill invalide : {name!r} (minuscules, chiffres, tirets)")
    if not description or not body:
        raise ValueError(f"skill {name!r} : description ou corps manquant")
    return {"name": name, "description": description, "body": PREAMBLE + "\n" + body}


def load_skills(directory: Path = SKILLS_DIR) -> list[dict]:
    skills = []
    for path in sorted(directory.glob("*.md")):
        try:
            skills.append(parse_skill(path.read_text(encoding="utf-8"), path.stem))
        except Exception as e:
            logger.warning("Skill ignoré ({}) : {}", path.name, e)
    return skills
