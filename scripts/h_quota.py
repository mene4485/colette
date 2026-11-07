"""Affiche le quota H et nettoie les « canaux » orphelins du bridge local.

    .venv/bin/python scripts/h_quota.py           # quota + canaux v1 en cours
    .venv/bin/python scripts/h_quota.py --clean   # supprime les canaux `pending` si aucune session n'est active

Pourquoi : le bridge user_device crée un canal (trajectoire v1, idle_timeout_s=1800) par session.
Quand un run est interrompu/planté, la session v2 finit `interrupted` mais le canal peut rester
`pending` ~30 min et occuper un slot du quota (3 sur le plan Free) → « platform rate-limited
channel setup ». DELETE /api/v1/trajectories/{id} libère le slot (non documenté, constaté le 7 nov).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import colette.archfix  # noqa: E402,F401

import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "colette" / ".env")
load_dotenv(ROOT / ".env")

BASE = os.getenv("HAI_BASE_URL", "https://agp.eu.hcompany.ai")
LIVE = ("queued", "pending", "running", "paused", "idle", "awaiting_tool_results")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--clean", action="store_true", help="supprime les canaux pending orphelins")
    args = p.parse_args()

    http = httpx.Client(base_url=BASE, headers={"Authorization": f"Bearer {os.environ['HAI_API_KEY']}"},
                        timeout=15, trust_env=False)
    print("Quota :", http.get("/api/v2/sessions/quota").json())

    sessions = http.get("/api/v2/sessions", params={"status": list(LIVE), "owner": "me"}).json()["items"]
    print(f"Sessions v2 actives : {len(sessions)}", [f"{s['id'][:8]} {s['status']}" for s in sessions])

    channels = [t for t in http.get("/api/v1/trajectories/", params={"size": 50}).json()["items"]
                if t["status"] in LIVE]
    # L'id du canal ≠ id de session : on ne peut pas les apparier, donc on ne nettoie
    # que lorsqu'aucune session n'est active (sinon on couperait le run en cours).
    orphans = not sessions
    if args.clean and not orphans:
        print("Une session est active : nettoyage refusé (arrête-la d'abord).")
    for t in channels:
        print(f"Canal {t['id'][:8]} {t['status']} créé {t['created_at'][:19]}Z{'  (orphelin)' if orphans else ''}")
        if args.clean and orphans and t["status"] == "pending":
            r = http.delete(f"/api/v1/trajectories/{t['id']}")
            print(f"  → DELETE {r.status_code}")
    if args.clean:
        print("Quota :", http.get("/api/v2/sessions/quota").json())


if __name__ == "__main__":
    main()
