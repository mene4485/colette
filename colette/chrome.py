"""Garantit un Chrome de l'agent sur :9222 avec au moins un onglet ouvert.

Sur macOS, fermer la dernière fenêtre laisse Chrome tourner sans aucune page :
chromedriver s'attache alors à une fenêtre inexistante ("no such window").
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import httpx
from loguru import logger

PORT = 9222
PROFILE = Path.home() / ".hai" / "chrome-profile"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def _get(path: str, method: str = "GET"):
    return httpx.request(method, f"http://127.0.0.1:{PORT}{path}", timeout=3.0, trust_env=False)


def _listening() -> bool:
    try:
        return _get("/json/version").status_code == 200
    except httpx.HTTPError:
        return False


def page_targets() -> list[dict]:
    return [t for t in _get("/json/list").json() if t.get("type") == "page"]


def ensure_chrome(start_url: str = "about:blank") -> None:
    if not _listening():
        PROFILE.mkdir(parents=True, exist_ok=True)
        logger.info("Lancement de Chrome (profil {})", PROFILE)
        subprocess.Popen(
            [CHROME, f"--remote-debugging-port={PORT}", f"--user-data-dir={PROFILE}",
             "--no-first-run", "--no-default-browser-check", start_url],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        deadline = time.monotonic() + 20
        while not _listening():
            if time.monotonic() > deadline:
                raise RuntimeError("Chrome n'a pas ouvert le port 9222")
            time.sleep(0.25)
    for _ in range(40):
        if page_targets():
            return
        logger.info("Chrome sans onglet → ouverture d'un onglet")
        try:
            _get(f"/json/new?{start_url}", method="PUT")
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    raise RuntimeError("Impossible d'ouvrir un onglet dans Chrome :9222")
