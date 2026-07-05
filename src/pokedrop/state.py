"""Persistent state: last-seen status per watch and which reminders have fired.

Kept as a small JSON file so it survives restarts and stays inspectable.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import data_dir


def _state_path() -> Path:
    return data_dir() / "state.json"


def load_state() -> dict:
    p = _state_path()
    if not p.exists():
        return {"watches": {}}
    try:
        with p.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {"watches": {}}
    data.setdefault("watches", {})
    return data


def save_state(state: dict) -> None:
    p = _state_path()
    tmp = p.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
    tmp.replace(p)


def get_watch_state(state: dict, watch_id: str) -> dict:
    return state["watches"].setdefault(
        watch_id,
        {"last_status": "unknown", "last_checked": None,
         "block_until": None, "fired_reminders": []},
    )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
