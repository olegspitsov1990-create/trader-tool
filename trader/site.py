"""Schreibt die JSON-Daten, die die Website (docs/) anzeigt."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .data import epoch_seconds
from .setups import SETUPS, TITLES

KEEP_SIGNALS = 1000
CHART_BARS = 150
OUTCOME_TEXT = {1: "oben", -1: "unten", 0: "kein Ausbruch"}


def _dir(root: Path, group: str) -> Path:
    p = root / "docs" / "data" / group
    (p / "charts").mkdir(parents=True, exist_ok=True)
    return p


def _dump(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def chart_file(symbol: str, tf: str) -> str:
    return f"{symbol.replace('/', '-').replace('^', '')}_{tf}.json"


def load_signals(root: Path, group: str) -> list[dict]:
    p = _dir(root, group) / "signals.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def resolve(signals: list[dict], prepared: dict[str, pd.DataFrame], tf: str) -> int:
    """Trägt bei offenen Signalen das tatsächliche Ergebnis nach (Live-Trefferquote)."""
    done = 0
    for s in signals:
        if s.get("outcome") is not None or s["tf"] != tf or s["symbol"] not in prepared:
            continue
        d = prepared[s["symbol"]]
        t = pd.Timestamp(s["bar_time"])
        if t in d.index and bool(d.at[t, "known"]):
            o = int(d.at[t, "outcome"])
            s["outcome"] = OUTCOME_TEXT[o]
            s["hit"] = (o == 1 and s["direction"] == "long") or (o == -1 and s["direction"] == "short")
            done += 1
    return done


def write_chart(root: Path, group: str, symbol: str, tf: str, d: pd.DataFrame, signals: list[dict]) -> None:
    tail = d.iloc[-(1300 if tf == "1d" else 400):]  # Tageskerzen ~5 Jahre (für die Chart-Ansicht ohne PC-Server)
    secs = epoch_seconds(tail.index)

    def col(name):
        return [None if (v is None or (isinstance(v, float) and math.isnan(v))) else round(float(v), 6)
                for v in tail[name].tolist()]

    start = tail.index[0]
    markers = [
        {"time": int(pd.Timestamp(s["bar_time"]).timestamp()), "direction": s["direction"], "title": s["title"]}
        for s in signals if s["symbol"] == symbol and s["tf"] == tf and pd.Timestamp(s["bar_time"]) >= start
    ]
    _dump(_dir(root, group) / "charts" / chart_file(symbol, tf), {
        "symbol": symbol, "tf": tf, "time": secs,
        "open": col("open"), "high": col("high"), "low": col("low"), "close": col("close"),
        "volume": [None if v != v else round(float(v)) for v in tail["volume"].tolist()], "markers": markers,
    })


def save(root: Path, group: str, signals: list[dict], stats_by_tf: dict, status: dict,
         overview_by_tf: dict | None = None) -> None:
    out = _dir(root, group)
    signals = sorted(signals, key=lambda s: s["bar_time"], reverse=True)[:KEEP_SIGNALS]
    _dump(out / "signals.json", signals)

    stats_json = {}
    for tf, table in stats_by_tf.items():
        rows = []
        for key, st in table["setups"].items():
            setup, trend = key.split("|")
            ud = st["up"] + st["down"]
            rows.append({
                "setup": setup, "title": TITLES[setup], "direction": SETUPS[setup][0], "trend": trend,
                "n": st["n"], "p_up": st["up"] / st["n"] if st["n"] else None,
                "p_down": st["down"] / st["n"] if st["n"] else None,
                "cond_up": st["up"] / ud if ud else None,
            })
        base = {t: {"n": b["n"], "cond_up": b["up"] / (b["up"] + b["down"]) if b["up"] + b["down"] else None,
                    "p_breakout": (b["up"] + b["down"]) / b["n"] if b["n"] else None}
                for t, b in table["baseline"].items()}
        stats_json[tf] = {"setups": rows, "baseline": base}
    _dump(out / "stats.json", stats_json)

    # Live-Trefferquote je Setup aus aufgelösten Signalen
    live: dict = {}
    for s in signals:
        if s.get("outcome") is None:
            continue
        e = live.setdefault(f"{s['tf']}|{s['setup']}", {"n": 0, "hits": 0})
        e["n"] += 1
        e["hits"] += int(bool(s.get("hit")))
    status["live"] = live
    status["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _dump(out / "status.json", status)

    # Charts ohne zugehöriges Signal entfernen
    overview_by_tf = overview_by_tf or {}
    _dump(out / "overview.json", overview_by_tf)
    keep = {chart_file(s["symbol"], s["tf"]) for s in signals}
    keep |= {chart_file(r["symbol"], tf) for tf, rows in overview_by_tf.items() for r in rows}
    for f in (out / "charts").glob("*.json"):
        if f.name not in keep:
            f.unlink()
