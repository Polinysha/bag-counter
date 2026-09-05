"""
Shared-secret API-key auth for the /api/v1/* routes.

Deliberately not a full user/session/OAuth system: this is a
single-tenant internal tool (one team operating one conveyor line, see
README), so one shared secret checked per request is proportionate to
the actual risk - a multi-user login system would be complexity this
project doesn't need. If that ever changes (multiple teams, external
customers), this is the module to replace, not extend.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import Header, HTTPException

from app.config import settings

log = logging.getLogger(__name__)


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """FastAPI dependency: raises 401 unless the request's X-API-Key
    header matches BC_API_KEY.

    If BC_API_KEY is unset, this is a no-op (open mode) - the default,
    so `docker compose up` still works out of the box for local/demo
    use without extra setup. See README "Security" and .env.example
    for how to require a key. main.py logs a warning at startup when
    running in open mode so it's not silently forgotten.
    """
    if not settings.api_key:
        return
    # constant-time comparison: a naive `!=` leaks how many leading
    # characters matched via response-timing, letting an attacker guess
    # the key one byte at a time. Irrelevant for a hobby project, cheap
    # to do right, so it's done right.
    if not x_api_key or not hmac.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(status_code=401, detail="Missing or invalid API key")
