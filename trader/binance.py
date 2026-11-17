"""Kerzendaten von Binance (öffentliche API, kein Konto nötig).

Hinweis: Binance sperrt Anfragen aus den USA – auf GitHub-Servern (USA) schlägt das fehl,
auf einem PC in Deutschland funktioniert es.
"""
from __future__ import annotations

import time

import pandas as pd
import requests

BASE = "https://api.binance.com"
DAYS = {"1m": 2, "1h": 730, "4h": 730, "1d": 1825}
_cache: dict[tuple[str, str], pd.DataFrame] = {}


def _fetch(symbol: str, interval: str, start_ms: int) -> list:
    rows: list = []
    while True:
        r = requests.get(f"{BASE}/api/v3/klines", timeout=20,
                         params={"symbol": symbol, "interval": interval, "limit": 1000, "startTime": start_ms})
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        rows += batch
        start_ms = batch[-1][0] + 1
        if len(batch) < 1000:
            break
    return rows


def history(symbol: str, tf: str) -> pd.DataFrame:
    """OHLCV-Historie; nach dem ersten Abruf werden nur neue Kerzen nachgeladen."""
    key = (symbol, tf)
    df = _cache.get(key)
    now_ms = int(time.time() * 1000)
    start = now_ms - DAYS[tf] * 86_400_000 if df is None or df.empty else int(df.index[-2].timestamp() * 1000)
    rows = _fetch(symbol, tf, start)
    new = pd.DataFrame([[r[0], *map(float, r[1:6])] for r in rows],
                       columns=["t", "open", "high", "low", "close", "volume"])
    new.index = pd.to_datetime(new.pop("t"), unit="ms", utc=True)
    df = new if df is None else pd.concat([df, new])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df[df.index >= pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=DAYS[tf])]
    _cache[key] = df
    return df.copy()


def prices(symbols: list[str]) -> dict[str, float]:
    r = requests.get(f"{BASE}/api/v3/ticker/price", timeout=10)
    r.raise_for_status()
    wanted = set(symbols)
    return {x["symbol"]: float(x["price"]) for x in r.json() if x["symbol"] in wanted}
