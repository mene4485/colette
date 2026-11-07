"""Libère les slots H laissés par le bridge local (user_device).

Chaque session user_device ouvre un « canal » (trajectoire v1, idle_timeout_s=1800). Même quand la
session finit bien, le canal reste `pending` ~30 min et occupe un slot du quota (3 sur le plan Free)
→ « platform rate-limited channel setup » au run suivant. DELETE /api/v1/trajectories/{id} le libère
(endpoint non documenté, constaté le 7 nov 2026). L'id du canal ≠ id de session : on cible les canaux
`pending` créés depuis le début du run.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

import httpx
from loguru import logger

BASE_URL = os.getenv("HAI_BASE_URL", "https://agp.eu.hcompany.ai")
LIVE = ("queued", "pending", "running", "paused", "idle", "awaiting_tool_results")


def _client_kwargs() -> dict:
    return {
        "base_url": BASE_URL,
        "headers": {"Authorization": f"Bearer {os.environ['HAI_API_KEY']}"},
        "timeout": 15.0,
        "trust_env": False,
    }


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


async def delete_pending_channels(since: Optional[datetime] = None) -> int:
    """Supprime les canaux `pending` (créés après `since` si fourni). Renvoie le nombre supprimé."""
    deleted = 0
    async with httpx.AsyncClient(**_client_kwargs()) as http:
        r = await http.get("/api/v1/trajectories/", params={"size": 50})
        r.raise_for_status()
        for t in r.json().get("items", []):
            if t.get("status") != "pending":
                continue
            if since is not None and _parse(t["created_at"]) < since:
                continue
            d = await http.delete(f"/api/v1/trajectories/{t['id']}")
            if d.status_code in (200, 204, 404):
                deleted += 1
            logger.info("Canal H {} supprimé ({})", t["id"][:8], d.status_code)
    return deleted


async def quota() -> dict:
    async with httpx.AsyncClient(**_client_kwargs()) as http:
        r = await http.get("/api/v2/sessions/quota")
        r.raise_for_status()
        return r.json()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
