"""Kerzen für die Chart-Ansicht (beliebige Zeiteinheit und Zeitraum, inkl. laufender Kerze).

Krypto: Binance · Aktien: Yahoo Finance. Ergebnisse werden kurz zwischengespeichert.
"""
from __future__ import annotations

import math
import threading
import time
from datetime import datetime, timezone

import pandas as pd
import requests

INTERVAL_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000,
               "1d": 86_400_000, "1w": 604_800_000, "1M": 2_629_800_000}
RANGE_DAYS = {"1D": 1, "5D": 5, "1M": 31, "3M": 92, "6M": 183, "1Y": 366, "2Y": 731, "5Y": 1827, "MAX": None}
EXTRA_BARS = 220  # Vorlauf, damit die SMA 200 ab dem ersten sichtbaren Tag berechnet ist
YAHOO_INTERVAL = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "60m", "4h": "60m", "1d": "1d", "1w": "1wk", "1M": "1mo"}
YAHOO_MAX_DAYS = {"1m": 7, "5m": 59, "15m": 59, "1h": 729, "4h": 729}
# ungefähre Kalendertage für 220 Vorlauf-Kerzen bei Aktien (Handelszeiten berücksichtigt)
YAHOO_EXTRA_DAYS = {"1m": 2, "5m": 6, "15m": 14, "1h": 50, "4h": 160, "1d": 330, "1w": 1600, "1M": 7000}

_cache: dict = {}
_lock = threading.Lock()


def _range_days(rng: str) -> float | None:
    if rng == "YTD":
        now = datetime.now(timezone.utc)
        return (now - datetime(now.year, 1, 1, tzinfo=timezone.utc)).days + 1
    return RANGE_DAYS.get(rng, 366)


def _binance(symbol: str, interval: str, rng: str) -> pd.DataFrame:
    days = _range_days(rng)
    step = INTERVAL_MS[interval]
    now = int(time.time() * 1000)
    if days is None:
        start = 1_500_000_000_000  # 2017 – Binance-Start
    else:
        start = now - int(days * 86_400_000) - EXTRA_BARS * step
    start = max(start, now - 5000 * step)  # höchstens 5000 Kerzen
    rows: list = []
    for base in ("https://api.binance.com", "https://data-api.binance.vision"):
        try:
            s = start
            rows = []
            while s < now:
                r = requests.get(f"{base}/api/v3/klines", timeout=15,
                                 params={"symbol": symbol, "interval": interval, "startTime": s, "limit": 1000})
                r.raise_for_status()
                batch = r.json()
                if not batch:
                    break
                rows += batch
                s = batch[-1][0] + 1
                if len(batch) < 1000:
                    break
            break
        except requests.RequestException:
            continue
    df = pd.DataFrame([[x[0], *map(float, x[1:6])] for x in rows],
                      columns=["t", "open", "high", "low", "close", "volume"])
    df.index = pd.to_datetime(df.pop("t"), unit="ms", utc=True)
    return df


def _yahoo_period(interval: str, rng: str) -> str:
    days = _range_days(rng)
    if interval in YAHOO_MAX_DAYS:
        need = (days or 10_000) + YAHOO_EXTRA_DAYS[interval]
        return f"{min(math.ceil(need), YAHOO_MAX_DAYS[interval])}d"
    if days is None:
        return "max"
    need = days + YAHOO_EXTRA_DAYS[interval]
    for label, d in (("1y", 366), ("2y", 731), ("5y", 1827), ("10y", 3653)):
        if need <= d:
            return label
    return "max"


def _yahoo(symbol: str, interval: str, rng: str) -> pd.DataFrame:
    import yfinance as yf

    df = yf.Ticker(symbol).history(period=_yahoo_period(interval, rng), interval=YAHOO_INTERVAL[interval],
                                   auto_adjust=True, prepost=False)
    if df.empty:
        return df
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna(subset=["close"])
    idx = pd.DatetimeIndex(df.index)
    df.index = (idx.tz_localize("America/New_York") if idx.tz is None else idx).tz_convert("UTC")
    if interval == "4h":  # 4h-Kerzen je Handelstag ab Eröffnung 9:30
        local = df.index.tz_convert("America/New_York")
        key = local.normalize() + pd.to_timedelta(((local - local.normalize() - pd.Timedelta(minutes=570))
                                                   // pd.Timedelta(hours=4)) * 4 * 3600 + 570 * 60, unit="s")
        df = df.groupby(key.tz_convert("UTC")).agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return df


def get(group: str, symbol: str, interval: str, rng: str) -> dict:
    if interval not in INTERVAL_MS:
        raise ValueError("unbekannte Zeiteinheit")
    key = (group, symbol, interval, rng)
    ttl = 20 if interval in ("1m", "5m", "15m") else 60
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
    df = _binance(symbol, interval, rng) if group == "crypto" else _yahoo(symbol, interval, rng)
    out = {
        "symbol": symbol, "interval": interval, "range": rng,
        "source": "Binance" if group == "crypto" else "Yahoo Finance",
        "time": (df.index.asi8 // 10**9).tolist(),
        **{c: [round(float(v), 6) for v in df[c].tolist()] for c in ("open", "high", "low", "close", "volume")},
    }
    with _lock:
        _cache[key] = (time.time(), out)
        if len(_cache) > 300:
            for k in sorted(_cache, key=lambda k: _cache[k][0])[:100]:
                _cache.pop(k, None)
    return out
