"""Marktübersicht: aktueller Zustand jedes überwachten Symbols (auch ohne Alarm)."""
from __future__ import annotations

import math

import pandas as pd

from .setups import SETUPS, TITLES


def _num(v, nd: int = 4):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else round(f, nd)


def row(d: pd.DataFrame, symbol: str, name: str, sector: str | None, table: dict) -> dict:
    last, prev = d.iloc[-1], d.iloc[-2]
    c, a = float(last["close"]), float(last["atr"])
    c20 = float(d["close"].iloc[-21]) if len(d) > 21 else float("nan")
    trend = last["trend"]
    base = table["baseline"].get(trend, {})
    base_up = base["up"] / (base["up"] + base["down"]) if base and base["up"] + base["down"] else 0.5

    active = []
    for s, (direction, _) in SETUPS.items():
        if not bool(last[s]):
            continue
        st = table["setups"].get(f"{s}|{trend}")
        if not st or st["up"] + st["down"] == 0:
            continue
        cond_up = st["up"] / (st["up"] + st["down"])
        d_eff = direction if direction != "neutral" else ("long" if cond_up >= base_up else "short")
        edge = (cond_up - base_up) if d_eff == "long" else (base_up - cond_up)
        active.append({"setup": s, "title": TITLES[s], "direction": d_eff, "cond_up": round(cond_up, 4),
                       "edge": round(edge, 4), "n": st["n"]})
    active.sort(key=lambda x: x["edge"], reverse=True)
    best = active[0] if active else None

    return {
        "symbol": symbol, "name": name, "sector": sector,
        "bar_time": d.index[-1].isoformat(),
        "close": _num(c, 6),
        "chg": _num(c / float(prev["close"]) - 1),
        "chg20": _num(c / c20 - 1),
        "trend": trend,
        "rsi": _num(last["rsi"], 1),
        "atr_pct": _num(a / c),
        "vol_ratio": _num(last["vol_ratio"], 2),
        "squeeze_len": int(last["squeeze_len"]),
        "dist_hh": _num((float(last["hh"]) - c) / a, 2),  # ATR bis zum 20er-Hoch (negativ = darüber)
        "dist_ll": _num((c - float(last["ll"])) / a, 2),  # ATR bis zum 20er-Tief (negativ = darunter)
        "above_ema50": bool(c > float(last["ema50"])),
        "setups": active,
        "cond_up": best["cond_up"] if best else round(base_up, 4),
        "edge": best["edge"] if best else 0.0,
        "direction": best["direction"] if best else None,
        "base_up": round(base_up, 4),
    }
