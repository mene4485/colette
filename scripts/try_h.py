"""Étape 1 — teste le mini-agent H sur l'espace abonné Free Mobile.

    .venv/bin/python scripts/try_h.py ["autre objectif"]

Ctrl+C une fois → cancel() propre (session `interrupted`). Deux fois → sortie immédiate.
Les events bruts sont écrits dans logs/h_events_*.jsonl.
"""

from __future__ import annotations

import asyncio
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import colette.archfix  # noqa: E402,F401  (relance en arm64 si Rosetta)

from dotenv import load_dotenv  # noqa: E402
from loguru import logger  # noqa: E402

load_dotenv(ROOT / "colette" / ".env")
load_dotenv(ROOT / ".env")

from colette.h_agent import DemarcheRunner, Step  # noqa: E402

GOAL = (
    "Va sur https://mobile.free.fr et ouvre l'espace abonné (Mon compte). "
    "Si une page de connexion apparaît, appelle ask_user pour demander à la personne de se "
    "connecter elle-même, puis attends sa réponse avant de continuer. "
    "Arrête-toi sur le tableau de bord de l'espace abonné et décris-le en deux phrases "
    "(forfait actuel, prix si visible). Ne clique sur rien d'autre."
)


async def main() -> None:
    logger.remove()
    logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | {level: <7} | {message}")

    goal = " ".join(sys.argv[1:]) or GOAL
    runner = DemarcheRunner()
    t0 = time.monotonic()

    def on_step(step: Step) -> None:
        dt = time.monotonic() - t0
        tag = {"step": "🗣 ", "page": "📄", "question": "❓", "status": "⏯ "}.get(step.kind, "• ")
        extra = f"  ({step.url})" if step.url and step.kind == "step" else ""
        print(f"[{dt:6.1f}s] {tag} {step.text}{extra}", flush=True)

    async def ask_user(question: str) -> str:
        print(f"\n❓ Agent : {question}", flush=True)
        if sys.stdin.isatty():
            return await asyncio.to_thread(input, "↳ Ta réponse (Entrée = « c'est fait ») : ") or "C'est fait."
        # Mode non interactif : la réponse est déposée dans logs/answer.txt
        answer_file = ROOT / "logs" / "answer.txt"
        answer_file.unlink(missing_ok=True)
        print(f"↳ En attente d'une réponse dans {answer_file}", flush=True)
        while not answer_file.exists():
            await asyncio.sleep(1)
        await asyncio.sleep(0.2)
        text = answer_file.read_text().strip()
        answer_file.unlink(missing_ok=True)
        print(f"↳ Réponse : {text}", flush=True)
        return text or "C'est fait."

    loop = asyncio.get_running_loop()
    presses = {"n": 0}

    def on_sigint() -> None:
        presses["n"] += 1
        if presses["n"] == 1:
            print("\n⏹  Ctrl+C → annulation de la session H… (re-Ctrl+C pour quitter)", flush=True)
            loop.create_task(runner.cancel())
        else:
            raise SystemExit(130)

    loop.add_signal_handler(signal.SIGINT, on_sigint)

    try:
        answer = await runner.run(goal, on_step=on_step, ask_user=ask_user)
    finally:
        await runner.aclose()
    print(f"\n✅ Status : {runner.status}  —  durée {time.monotonic() - t0:.0f}s  —  session {runner.session_id}")
    print(f"Réponse : {answer}")


if __name__ == "__main__":
    asyncio.run(main())
