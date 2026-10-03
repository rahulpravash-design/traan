"""Single choke point for operator commands (alert, confirm, reject; later: no-fly, recall).

CLAUDE.md rule: every command goes through the signed, human-confirmed path. In the 50% build
this function only checks that a human is named and writes an audit line; module 9 adds
JWT roles and command signatures HERE, so no caller has to change.
"""
from __future__ import annotations

import json
import logging
import time

from fastapi import HTTPException

audit = logging.getLogger("traan.audit")


def authorize_command(kind: str, payload: dict) -> None:
    if not payload.get("by"):
        raise HTTPException(403, "commands must name the human who issued them")
    # TODO(module 9): verify JWT role + Ed25519 signature over (kind, payload, ts) before accepting.
    audit.info(json.dumps({"ts": time.time(), "kind": kind, **payload}))
