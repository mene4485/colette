"""Colette — point d'entrée unique : bulle (CDP) + voix (micro/HP du laptop) + agent H.

    .venv/bin/python scripts/run_colette.py --fake   # faux agent H (aucune session H consommée)
    .venv/bin/python scripts/run_colette.py          # vrai agent H (coûte une session H)

Cliquer sur la bulle dans le Chrome :9222 → Colette dit bonjour et écoute.
Options : --auto (ouvre la bulle et parle sans clic), --say "phrase" (répétable : simule la
personne sans micro ; « ?phrase » = réponse à la prochaine question de l'agent H).
Variables : OPENROUTER_MODEL, COLETTE_BARGE_IN=1 (casque : on peut couper la parole à Colette).
Ctrl+C pour quitter.
"""

from __future__ import annotations

import argparse
import asyncio
import os
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

# Python de python.org sans magasin de certificats : websockets/aiohttp (Gladia, Cartesia) échouent
# en CERTIFICATE_VERIFY_FAILED. On utilise le bundle certifi.
import certifi  # noqa: E402

os.environ.setdefault("SSL_CERT_FILE", certifi.where())

from colette.chrome import ensure_chrome  # noqa: E402
from colette.overlay import OverlayInjector  # noqa: E402
from colette.state import StateServer  # noqa: E402


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--fake", action="store_true", help="faux agent H (scénario rejoué)")
    p.add_argument("--url", default="https://mobile.free.fr/")
    p.add_argument("--auto", action="store_true", help="ouvre la bulle et dit bonjour sans clic")
    p.add_argument("--say", action="append", default=[], help="phrase simulée (répétable)")
    p.add_argument("--debug", action="store_true")
    args = p.parse_args()

    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if args.debug else "INFO",
               format="<green>{time:HH:mm:ss.SSS}</green> | {level: <7} | {message}")

    from colette.voice import ColetteVoice  # import lourd (pipecat) après le logger

    await asyncio.to_thread(ensure_chrome, args.url)
    server = StateServer()
    await server.start()
    injector = OverlayInjector(server)
    inject_task = asyncio.create_task(injector.run_forever())

    if args.fake:
        from colette.fake_runner import FakeDemarcheRunner

        runner = FakeDemarcheRunner()
    else:
        from colette.h_agent import DemarcheRunner

        runner = DemarcheRunner()

    voice = ColetteVoice(server, runner, script=args.say, auto_open=args.auto or bool(args.say))
    voice_task = asyncio.create_task(voice.run())

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, stop.set)
    loop.add_signal_handler(signal.SIGTERM, stop.set)
    voice_task.add_done_callback(lambda _t: stop.set())
    logger.info("Prêt ({}). Ouvre {} dans le Chrome :9222 et clique sur la bulle. Ctrl+C pour quitter.",
                "faux agent H" if args.fake else "vrai agent H", args.url)
    await stop.wait()

    logger.info("Arrêt…")
    try:
        await runner.cancel()
        await runner.aclose()
    except Exception as e:
        logger.warning("Arrêt de l'agent : {}", e)
    await voice.stop()
    try:
        await asyncio.wait_for(voice_task, 5)
    except (asyncio.TimeoutError, asyncio.CancelledError, Exception) as e:
        logger.debug("Fin du pipeline voix : {!r}", e)
    inject_task.cancel()
    await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
