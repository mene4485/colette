"""Garantit un Chrome de l'agent sur :9222 avec au moins un onglet ouvert (macOS, Windows, Linux).

Sur macOS, fermer la dernière fenêtre laisse Chrome tourner sans aucune page :
chromedriver s'attache alors à une fenêtre inexistante ("no such window").
Chemin de Chrome : détecté automatiquement, ou variable d'environnement CHROME_PATH.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
from loguru import logger

PORT = 9222
PROFILE = Path.home() / ".hai" / "chrome-profile"
IS_WINDOWS = sys.platform == "win32"
MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def find_chrome() -> str:
    """Chemin de l'exécutable Chrome (CHROME_PATH d'abord)."""
    env = os.getenv("CHROME_PATH")
    if env:
        return env
    if IS_WINDOWS:
        candidates = [
            os.path.join(os.environ[var], "Google", "Chrome", "Application", "chrome.exe")
            for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")
            if os.environ.get(var)
        ]
    elif sys.platform == "darwin":
        candidates = [MAC_CHROME, str(Path.home() / MAC_CHROME.lstrip("/"))]
    else:
        candidates = [shutil.which(n) or "" for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    raise RuntimeError("Chrome introuvable : installe Google Chrome ou définis CHROME_PATH dans .env")


def _get(path: str, method: str = "GET"):
    return httpx.request(method, f"http://127.0.0.1:{PORT}{path}", timeout=3.0, trust_env=False)


def _listening() -> bool:
    try:
        return _get("/json/version").status_code == 200
    except httpx.HTTPError:
        return False


def page_targets() -> list[dict]:
    return [t for t in _get("/json/list").json() if t.get("type") == "page"]


# Écran HiDPI (Mac Retina, Windows à 125–200 %) : le bridge local de H convertit les coordonnées
# de clic avec la taille de la capture (pixels physiques) au lieu du viewport (pixels CSS) → chaque
# clic tombe décalé, souvent hors de la page (constaté le 7 nov sur Mac : cursor_position = 2 × cible).
# Chrome en facteur d'échelle 1 → capture = viewport → clics justes.
SCALE_FLAG = "--force-device-scale-factor=1"


def _process_list() -> list[tuple[int, str]]:
    """(pid, ligne de commande) des processus Chrome."""
    if IS_WINDOWS:
        ps = ("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
              "ForEach-Object { \"$($_.ProcessId) $($_.CommandLine)\" }")
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                             capture_output=True, text=True, encoding="utf-8", errors="replace",
                             creationflags=subprocess.CREATE_NO_WINDOW).stdout
    else:
        out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout
    procs = []
    for line in out.splitlines():
        pid, _, cmd = line.strip().partition(" ")
        if pid.isdigit():
            procs.append((int(pid), cmd))
    return procs


def _running_without_scale_flag() -> list[int]:
    """PIDs du Chrome :9222 (processus principal) lancé sans SCALE_FLAG."""
    return [pid for pid, cmd in _process_list()
            if f"--remote-debugging-port={PORT}" in cmd and "--type=" not in cmd and SCALE_FLAG not in cmd]


def _kill(pid: int, force: bool = False) -> None:
    if IS_WINDOWS:
        cmd = ["taskkill", "/PID", str(pid), "/T"] + (["/F"] if force else [])
        subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        subprocess.run(["kill", "-KILL" if force else "-TERM", str(pid)])


def _restart_if_scaled() -> None:
    pids = _running_without_scale_flag()
    if not pids:
        return
    logger.warning("Chrome :9222 tourne sans {} (clics de H décalés sur écran HiDPI) → redémarrage", SCALE_FLAG)
    for pid in pids:
        _kill(pid)
    deadline = time.monotonic() + 15
    while _listening() and time.monotonic() < deadline:
        time.sleep(0.25)
    if _listening():  # fermeture douce refusée : on force
        for pid in pids:
            _kill(pid, force=True)
        time.sleep(1.0)
    time.sleep(1.0)  # laisse Chrome libérer le profil


def _launch(start_url: str) -> None:
    PROFILE.mkdir(parents=True, exist_ok=True)
    chrome = find_chrome()
    logger.info("Lancement de Chrome {} (profil {})", chrome, PROFILE)
    args = [chrome, f"--remote-debugging-port={PORT}", f"--user-data-dir={PROFILE}", SCALE_FLAG,
            "--no-first-run", "--no-default-browser-check", start_url]
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if IS_WINDOWS:  # Chrome survit à la fermeture de la console / au Ctrl+C
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(args, **kwargs)


def open_tab(url: str) -> None:
    """Ouvre `url` dans un nouvel onglet du Chrome :9222, sauf si un onglet y est déjà."""
    if any((t.get("url") or "").startswith(url) for t in page_targets()):
        return
    _get(f"/json/new?{url}", method="PUT")


def ensure_chrome(start_url: str = "about:blank") -> None:
    if _listening():
        _restart_if_scaled()
    if not _listening():
        _launch(start_url)
        deadline = time.monotonic() + 20
        while not _listening():
            if time.monotonic() > deadline:
                raise RuntimeError("Chrome n'a pas ouvert le port 9222 (un Chrome déjà ouvert avec ce profil ?)")
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
