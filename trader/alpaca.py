"""Live-Aktienkurse über Alpaca (kostenloser Datenfeed IEX, Konto nötig).

Zugangsdaten aus Umgebungsvariablen / .env: ALPACA_KEY_ID, ALPACA_SECRET_KEY
"""
from __future__ import annotations

import os

import requests

URL = "https://data.alpaca.markets/v2/stocks/snapshots"


def configured() -> bool:
    return bool(os.environ.get("ALPACA_KEY_ID") and os.environ.get("ALPACA_SECRET_KEY"))


def snapshots(symbols: list[str], feed: str = "iex") -> dict[str, dict]:
    """Letzter Kurs je Symbol: {"AAPL": {"p": 189.5, "t": "...", "prev": 188.1}}"""
    headers = {"APCA-API-KEY-ID": os.environ["ALPACA_KEY_ID"].strip(),
               "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET_KEY"].strip()}
    out: dict[str, dict] = {}
    for i in range(0, len(symbols), 200):
        chunk = [s.replace("-", ".") for s in symbols[i:i + 200]]
        r = requests.get(URL, headers=headers, timeout=20, params={"symbols": ",".join(chunk), "feed": feed})
        r.raise_for_status()
        payload = r.json()
        payload = payload.get("snapshots", payload)
        for sym, snap in payload.items():
            if not snap:
                continue
            trade = snap.get("latestTrade") or {}
            if trade.get("p") is None:
                continue
            out[sym.replace(".", "-")] = {
                "p": float(trade["p"]), "t": trade.get("t"),
                "prev": (snap.get("prevDailyBar") or {}).get("c"),
            }
    return out
