"""Erkennung von Kauf-/Verkaufs-Setups und Erzeugung von Signalen."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

# Name -> (Richtung, Beschreibung)
SETUPS: dict[str, tuple[str, str]] = {
    "AUSBRUCH_OBEN": ("long", "Schluss über dem Hoch der letzten Kerzen mit erhöhtem Volumen"),
    "AUSBRUCH_UNTEN": ("short", "Schluss unter dem Tief der letzten Kerzen mit erhöhtem Volumen"),
    "SQUEEZE": ("neutral", "Volatilitäts-Squeeze (Bollinger in Keltner) – Ausbruch baut sich auf"),
    "RSI_UMKEHR_LONG": ("long", "RSI kreuzt 30 von unten (überverkauft → Erholung)"),
    "RSI_UMKEHR_SHORT": ("short", "RSI kreuzt 70 von oben (überkauft → Schwäche)"),
    "EMA_KREUZ_OBEN": ("long", "EMA 20 kreuzt EMA 50 nach oben"),
    "EMA_KREUZ_UNTEN": ("short", "EMA 20 kreuzt EMA 50 nach unten"),
    "ENGULFING_BULLISCH": ("long", "Bullische Engulfing-Kerze nahe dem Tief"),
    "ENGULFING_BAERISCH": ("short", "Bärische Engulfing-Kerze nahe dem Hoch"),
}

TITLES = {
    "AUSBRUCH_OBEN": "Ausbruch nach oben", "AUSBRUCH_UNTEN": "Ausbruch nach unten",
    "SQUEEZE": "Squeeze", "RSI_UMKEHR_LONG": "RSI-Umkehr long", "RSI_UMKEHR_SHORT": "RSI-Umkehr short",
    "EMA_KREUZ_OBEN": "EMA-Kreuz oben", "EMA_KREUZ_UNTEN": "EMA-Kreuz unten",
    "ENGULFING_BULLISCH": "Bullisches Engulfing", "ENGULFING_BAERISCH": "Bärisches Engulfing",
}


def detect(d: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    d = d.copy()
    vf = float(cfg.get("volume_factor", 1.5))
    sq_min = int(cfg.get("squeeze_min_bars", 5))
    lb = int(cfg.get("breakout_lookback", 20))
    o, c, h, lo = d["open"], d["close"], d["high"], d["low"]
    vol_ok = d["vol_ratio"].fillna(0) >= vf
    # Ohne Volumendaten (z. B. manche Indizes) Volumenfilter ignorieren
    if (d["volume"] == 0).mean() > 0.5:
        vol_ok = pd.Series(True, index=d.index)

    d["AUSBRUCH_OBEN"] = (c > d["hh"]) & (c.shift(1) <= d["hh"].shift(1)) & vol_ok
    d["AUSBRUCH_UNTEN"] = (c < d["ll"]) & (c.shift(1) >= d["ll"].shift(1)) & vol_ok
    d["SQUEEZE"] = d["squeeze_len"] == sq_min
    d["RSI_UMKEHR_LONG"] = (d["rsi"] > 30) & (d["rsi"].shift(1) <= 30)
    d["RSI_UMKEHR_SHORT"] = (d["rsi"] < 70) & (d["rsi"].shift(1) >= 70)
    d["EMA_KREUZ_OBEN"] = (d["ema20"] > d["ema50"]) & (d["ema20"].shift(1) <= d["ema50"].shift(1))
    d["EMA_KREUZ_UNTEN"] = (d["ema20"] < d["ema50"]) & (d["ema20"].shift(1) >= d["ema50"].shift(1))
    near_low = (lo - lo.rolling(lb).min()) <= 0.5 * d["atr"]
    near_high = (h.rolling(lb).max() - h) <= 0.5 * d["atr"]
    prev_red, prev_green = c.shift(1) < o.shift(1), c.shift(1) > o.shift(1)
    d["ENGULFING_BULLISCH"] = prev_red & (c > o) & (c >= o.shift(1)) & (o <= c.shift(1)) & near_low
    d["ENGULFING_BAERISCH"] = prev_green & (c < o) & (c <= o.shift(1)) & (o >= c.shift(1)) & near_high
    for s in SETUPS:
        d[s] = d[s].fillna(False).astype(bool)
    return d


def signals_on_last_bar(d: pd.DataFrame, symbol: str, tf: str, group: str, table: dict,
                        acfg: dict, alcfg: dict) -> list[dict]:
    row = d.iloc[-1]
    k = float(acfg.get("barrier_atr", 1.5))
    out = []
    for name, (direction, label) in SETUPS.items():
        if not bool(row[name]):
            continue
        st = table["setups"].get(f"{name}|{row['trend']}")
        if not st or st["n"] < int(alcfg.get("min_samples", 30)) or st["up"] + st["down"] == 0:
            continue
        cond_up = st["up"] / (st["up"] + st["down"])
        base = table["baseline"].get(row["trend"], {})
        base_up = base["up"] / (base["up"] + base["down"]) if base and base["up"] + base["down"] else 0.5
        if direction == "neutral":
            direction = "long" if cond_up >= 0.5 else "short"
        score = cond_up if direction == "long" else 1 - cond_up
        edge = score - (base_up if direction == "long" else 1 - base_up)
        if score < float(alcfg.get("min_probability", 0.55)) or edge < float(alcfg.get("min_edge", 0.05)):
            continue
        t = d.index[-1]
        out.append({
            "id": f"{group}|{symbol}|{tf}|{name}|{t.isoformat()}",
            "group": group, "symbol": symbol, "tf": tf, "setup": name,
            "title": TITLES[name], "label": label, "direction": direction,
            "bar_time": t.isoformat(), "close": float(row["close"]), "atr": float(row["atr"]),
            "level_up": float(row["close"] + k * row["atr"]), "level_down": float(row["close"] - k * row["atr"]),
            "p_breakout": (st["up"] + st["down"]) / st["n"],
            "p_up": st["up"] / st["n"], "p_down": st["down"] / st["n"],
            "cond_up": cond_up, "score": score, "base_up": base_up,
            "edge": edge,
            "n": st["n"], "trend": row["trend"], "rsi": float(row["rsi"]),
            "vol_ratio": None if pd.isna(row["vol_ratio"]) else float(row["vol_ratio"]),
            "outcome": None, "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
    return out
