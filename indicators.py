"""Technische Indikatoren (nur pandas/numpy, keine Zusatzbibliothek nötig)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def add_indicators(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    d = df.copy()
    c = d["close"]
    lb = int(cfg.get("breakout_lookback", 20))

    d["ema20"], d["ema50"], d["ema200"] = ema(c, 20), ema(c, 50), ema(c, 200)
    d["rsi"] = rsi(c)
    d["atr"] = atr(d)

    mid = c.rolling(20).mean()
    sd = c.rolling(20).std()
    bb_up, bb_lo = mid + 2 * sd, mid - 2 * sd
    kc_up, kc_lo = d["ema20"] + 1.5 * d["atr"], d["ema20"] - 1.5 * d["atr"]
    sq = ((bb_up < kc_up) & (bb_lo > kc_lo)).fillna(False)
    d["squeeze"] = sq
    d["squeeze_len"] = sq.astype(int).groupby((~sq).cumsum()).cumsum()

    vol_avg = d["volume"].rolling(20).mean().shift(1)
    d["vol_ratio"] = (d["volume"] / vol_avg.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)

    d["hh"] = d["high"].rolling(lb).max().shift(1)
    d["ll"] = d["low"].rolling(lb).min().shift(1)
    d["trend"] = np.where(c > d["ema200"], "auf", "ab")
    return d
