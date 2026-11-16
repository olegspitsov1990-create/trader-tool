"""Merkt sich verarbeitete Kerzen und Cooldowns zwischen den Läufen."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .data import TF_DELTA


def load(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"last_bar": {}, "last_signal": {}}


def save(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=1, sort_keys=True), encoding="utf-8")


def is_new_bar(state: dict, key: str, t: pd.Timestamp) -> bool:
    prev = state["last_bar"].get(key)
    return prev is None or pd.Timestamp(prev) < t


def set_bar(state: dict, key: str, t: pd.Timestamp) -> None:
    state["last_bar"][key] = t.isoformat()


def in_cooldown(state: dict, sig: dict, bars: int) -> bool:
    key = f"{sig['symbol']}|{sig['tf']}|{sig['setup']}"
    prev = state["last_signal"].get(key)
    if prev is None:
        return False
    return pd.Timestamp(sig["bar_time"]) - pd.Timestamp(prev) < TF_DELTA[sig["tf"]] * bars


def mark(state: dict, sig: dict) -> None:
    state["last_signal"][f"{sig['symbol']}|{sig['tf']}|{sig['setup']}"] = sig["bar_time"]
