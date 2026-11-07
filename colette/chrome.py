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


# Mac Retina : le bridge local de H convertit les coordonnées de clic avec la taille de la capture
# (pixels physiques, ×2) au lieu du viewport (pixels CSS) → chaque clic tombe au double de la
# position visée, souvent hors de la page (constaté le 7 nov : cursor_position = 2 × cible).
# Chrome en facteur d'échelle 1 → capture = viewport → clics justes.
SCALE_FLAG = "--force-device-scale-factor=1"


def _running_without_scale_flag() -> list[int]:
    """PIDs du Chrome :9222 (processus principal) lancé sans SCALE_FLAG."""
    out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout
    pids = []
    for line in out.splitlines():
        pid, _, cmd = line.strip().partition(" ")
        if f"--remote-debugging-port={PORT}" in cmd and "--type=" not in cmd and SCALE_FLAG not in cmd:
            pids.append(int(pid))
    return pids


def _restart_if_scaled() -> None:
    pids = _running_without_scale_flag()
    if not pids:
        return
    logger.warning("Chrome :9222 tourne sans {} (clics de H décalés sur Retina) → redémarrage", SCALE_FLAG)
    for pid in pids:
        subprocess.run(["kill", "-TERM", str(pid)])
    deadline = time.monotonic() + 15
    while _listening() and time.monotonic() < deadline:
        time.sleep(0.25)
    time.sleep(1.0)  # laisse Chrome libérer le profil


def ensure_chrome(start_url: str = "about:blank") -> None:
    if _listening():
        _restart_if_scaled()
    if not _listening():
        PROFILE.mkdir(parents=True, exist_ok=True)
        logger.info("Lancement de Chrome (profil {})", PROFILE)
        subprocess.Popen(
            [CHROME, f"--remote-debugging-port={PORT}", f"--user-data-dir={PROFILE}", SCALE_FLAG,
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
