"""Offline-Test mit synthetischen Kursen (ohne Internet, ohne E-Mail).

Aufruf:  python tests/test_offline.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import run as runner  # noqa: E402

NOW = datetime(2026, 11, 16, 22, 0, tzinfo=timezone.utc)


def fake_series(seed: int, freq: str, periods: int, tz: str) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    end = pd.Timestamp(NOW).tz_convert(tz).floor("h" if freq == "h" else "D")
    idx = pd.date_range(end=end, periods=periods, freq=freq)
    ret = rng.normal(0.0002, 0.01, periods)
    close = 100 * np.exp(np.cumsum(ret))
    open_ = np.r_[close[0], close[:-1]]
    spread = np.abs(rng.normal(0, 0.006, periods)) * close
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    vol = rng.lognormal(10, 0.5, periods)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=idx)


def provider(symbols, tf, market):
    out = {}
    for i, s in enumerate(symbols):
        if tf == "1d":
            df = fake_series(i, "B" if market == "stocks" else "D", 1250, "America/New_York" if market == "stocks" else "UTC")
            if market == "stocks":
                df.index = df.index.tz_localize(None)  # wie yfinance: Datum ohne Zeitzone
        else:
            df = fake_series(i + 100, "h", 24 * 700, "UTC")
            if tf == "4h":
                df = runner.data._resample_4h(df)
        out[s] = df
    return out


def universe():
    syms = [f"T{i:03d}" for i in range(40)]
    return pd.DataFrame({"symbol": syms, "name": [f"Testfirma {s}" for s in syms], "sector": "Test"})


def main():
    tmp = Path(tempfile.mkdtemp())
    for sub in ("config", "docs"):
        shutil.copytree(ROOT / sub, tmp / sub)
    for group in ("crypto", "stocks"):
        sigs = runner.run(group, dry_run=True, root=tmp, provider=provider, universe=universe, now=NOW)
        print(f"{group}: {len(sigs)} neue Signale")
        again = runner.run(group, dry_run=True, root=tmp, provider=provider, universe=universe, now=NOW)
        assert again == [], "Zweiter Lauf auf denselben Kerzen darf keine Signale doppelt senden"
        stats = json.loads((tmp / "docs/data" / group / "stats.json").read_text())
        for tf, st in stats.items():
            total = sum(r["n"] for r in st["setups"])
            print(f"  {tf}: {total} historische Setup-Fälle, Basis ↑ {st['baseline']['auf']['cond_up']:.2f}")
    print("Ausgabe:", tmp)
    return tmp


if __name__ == "__main__":
    main()
