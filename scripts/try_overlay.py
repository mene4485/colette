"""Étape 2 — bulle Colette injectée via CDP dans le Chrome :9222.

    .venv/bin/python scripts/try_overlay.py --demo      # scénario simulé, sans H
    .venv/bin/python scripts/try_overlay.py --with-h    # vrai agent H (coûte une session H)

Options : --url (page à ouvrir si Chrome n'a pas d'onglet), --auto (démarre sans clic sur la bulle).
Cliquer sur la bulle (message « open ») lance le scénario. Ctrl+C pour quitter.
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import colette.archfix  # noqa: E402,F401  (relance en arm64 si Rosetta)

from dotenv import load_dotenv  # noqa: E402
from loguru import logger  # noqa: E402

load_dotenv(ROOT / "colette" / ".env")
load_dotenv(ROOT / ".env")

from colette.chrome import ensure_chrome  # noqa: E402
from colette.overlay import OverlayInjector  # noqa: E402
from colette.state import StateServer  # noqa: E402

DEMO_STEPS = [
    "Comprendre votre demande",
    "Ouvrir votre espace abonné",
    "Choisir le nouveau forfait",
    "Confirmer le changement",
    "Terminé",
]

H_GOAL = (
    "Va sur https://mobile.free.fr/account/ (espace abonné). "
    "Si une page de connexion apparaît, appelle ask_user pour demander à la personne de se "
    "connecter elle-même, puis attends sa réponse avant de continuer. "
    "Arrête-toi sur le tableau de bord de l'espace abonné et décris-le en deux phrases "
    "(forfait actuel, prix si visible). Ne clique sur rien d'autre."
)


class Scenario:
    """Lance / annule / met en pause une tâche de fond pilotée par les messages de la bulle."""

    def __init__(self, server: StateServer, once: bool = False) -> None:
        self.server = server
        self.once = once  # --with-h : une seule session H par process (quota de 3)
        self.started = False
        self.task: asyncio.Task | None = None
        self.resumed = asyncio.Event()
        self.resumed.set()

    async def checkpoint(self) -> None:
        await self.resumed.wait()

    async def say(self, text: str, pause: float = 2.0) -> None:
        await self.checkpoint()
        self.server.set_subtitle(text)
        await asyncio.sleep(pause)
        await self.checkpoint()

    def start(self, coro_fn) -> None:
        if self.task and not self.task.done():
            return
        if self.once and self.started:
            logger.info("Session H déjà lancée une fois : relance le script pour un nouvel essai.")
            return
        self.started = True
        self.resumed.set()
        self.task = asyncio.create_task(coro_fn())

    def cancel(self) -> None:
        if self.task and not self.task.done():
            self.task.cancel()


async def demo_flow(sc: Scenario) -> None:
    s = sc.server
    s.set_steps(DEMO_STEPS)
    s.set_status("speaking")
    await sc.say("Bonjour, que puis-je faire pour vous ?")
    s.set_status("listening")
    await sc.say("« Mon forfait est trop cher. »", 2.5)
    s.set_status("working")
    s.advance_step()
    await sc.say("D'accord, je vais regarder votre forfait.")
    s.advance_step()
    await sc.say("J'ouvre votre espace abonné Free Mobile.", 3)
    s.advance_step()
    await sc.say("Il existe un forfait à 2 € par mois. Je le sélectionne.", 3)
    s.advance_step()
    ok = await s.ask_confirm("Je change votre forfait pour celui à 2 € par mois. On valide ?")
    logger.info("ask_confirm résolu → {}", ok)
    s.set_status("working")
    if ok:
        await sc.say("Très bien, je valide le changement.", 2.5)
        s.finish_steps()
        s.set_status("done")
        s.set_subtitle("C'est fait : votre forfait à 2 € démarre le 1er décembre.")
    else:
        s.set_status("done")
        s.set_subtitle("D'accord, je ne change rien. Votre forfait reste le même.")


async def h_flow(sc: Scenario, runner) -> None:
    from colette.h_agent import Step

    s = sc.server
    s.update(steps=[], status="working")
    s.set_subtitle("Je m'occupe de votre espace abonné…")

    def on_step(step: Step) -> None:
        print(f"[{step.kind}] {step.text}", flush=True)
        if step.kind == "step":
            s.add_step(step.text[:80])
            s.set_subtitle(step.text)
        elif step.kind == "question":
            s.set_subtitle(step.text)

    async def ask_user(question: str) -> str:
        # Étape 2 : réponse au clavier (la voix arrive à l'étape 3).
        s.set_status("listening")
        print(f"\n❓ {question}", flush=True)
        if sys.stdin.isatty():
            answer = await asyncio.to_thread(input, "↳ Réponse (Entrée = « c'est fait ») : ")
        else:  # non interactif : réponse déposée dans logs/answer.txt
            answer_file = ROOT / "logs" / "answer.txt"
            answer_file.unlink(missing_ok=True)
            print(f"↳ En attente d'une réponse dans {answer_file}", flush=True)
            while not answer_file.exists():
                await asyncio.sleep(1)
            await asyncio.sleep(0.2)
            answer = answer_file.read_text().strip()
            answer_file.unlink(missing_ok=True)
        s.set_status("working")
        return answer or "C'est fait."

    answer = await runner.run(H_GOAL, on_step=on_step, ask_user=ask_user)
    s.finish_steps()
    s.set_status("done")
    s.set_subtitle(answer or "C'est terminé.")
    print(f"\n✅ {runner.status} — {answer}", flush=True)


async def main() -> None:
    p = argparse.ArgumentParser()
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--demo", action="store_true")
    mode.add_argument("--with-h", action="store_true")
    p.add_argument("--url", default="https://mobile.free.fr/")
    p.add_argument("--auto", action="store_true", help="démarre le scénario sans attendre le clic")
    args = p.parse_args()

    logger.remove()
    logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | {level: <7} | {message}")

    await asyncio.to_thread(ensure_chrome, args.url)
    server = StateServer()
    await server.start()
    injector = OverlayInjector(server)
    inject_task = asyncio.create_task(injector.run_forever())

    sc = Scenario(server, once=args.with_h)
    runner = None
    if args.with_h:
        from colette.h_agent import DemarcheRunner

        runner = DemarcheRunner()
        flow = lambda: h_flow(sc, runner)  # noqa: E731
    else:
        flow = lambda: demo_flow(sc)  # noqa: E731

    async def on_message(msg: dict) -> None:
        t = msg["type"]
        if t == "open":
            sc.start(flow)
        elif t == "pause":
            sc.resumed.clear()
            if runner:
                await runner.pause()
        elif t == "resume":
            sc.resumed.set()
            if runner:
                await runner.resume()
        elif t == "stop":
            if runner:
                await runner.cancel()
            sc.cancel()
            server.set_subtitle("D'accord, j'arrête tout.")

    server.on_client_message(on_message)
    if args.auto:
        server.set_open(True)
        sc.start(flow)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, stop.set)
    logger.info("Prêt. Ouvre {} dans le Chrome :9222 et clique sur la bulle. Ctrl+C pour quitter.", args.url)
    await stop.wait()

    logger.info("Arrêt…")
    if runner:
        try:
            await runner.cancel()
            await runner.aclose()
        except Exception as e:
            logger.warning("Arrêt de la session H : {}", e)
    sc.cancel()
    inject_task.cancel()
    await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
