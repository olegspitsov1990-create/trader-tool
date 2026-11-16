"""Historische Ausbruchsstatistik (Triple-Barrier, symmetrisch)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .setups import SETUPS

WARMUP = 200


def label_outcomes(d: pd.DataFrame, cfg: dict) -> tuple[np.ndarray, np.ndarray]:
    """Für jede Kerze: +1 = Kurs erreicht zuerst +k·ATR, -1 = zuerst -k·ATR,
    0 = keins von beiden innerhalb des Zeitfensters (oder beide in derselben Kerze).
    known = Ergebnis steht bereits fest."""
    horizon = int(cfg.get("horizon_bars", 10))
    k = float(cfg.get("barrier_atr", 1.5))
    c, h, lo, a = (d[x].to_numpy(dtype=float) for x in ("close", "high", "low", "atr"))
    n = len(c)
    up_lvl, dn_lvl = c + k * a, c - k * a
    first_up = np.full(n, np.inf)
    first_dn = np.full(n, np.inf)
    for step in range(1, horizon + 1):
        hk = np.full(n, np.nan)
        lk = np.full(n, np.nan)
        hk[:-step] = h[step:]
        lk[:-step] = lo[step:]
        with np.errstate(invalid="ignore"):
            hit_u = (hk >= up_lvl) & np.isinf(first_up)
            hit_d = (lk <= dn_lvl) & np.isinf(first_dn)
        first_up[hit_u] = step
        first_dn[hit_d] = step
    outcome = np.where(first_up < first_dn, 1, np.where(first_dn < first_up, -1, 0))
    idx = np.arange(n)
    known = ((idx + horizon <= n - 1) | np.isfinite(np.minimum(first_up, first_dn))) & (idx >= WARMUP) & ~np.isnan(a)
    return outcome, known


def _add(acc: dict, key: str, o: np.ndarray) -> None:
    s = acc.setdefault(key, {"n": 0, "up": 0, "down": 0})
    s["n"] += int(len(o))
    s["up"] += int((o == 1).sum())
    s["down"] += int((o == -1).sum())


def aggregate(prepared: dict[str, pd.DataFrame]) -> dict:
    setups: dict = {}
    baseline: dict = {}
    for d in prepared.values():
        k = d[d["known"]]
        o = k["outcome"].to_numpy()
        tr = k["trend"].to_numpy()
        for t in ("auf", "ab"):
            m = tr == t
            _add(baseline, t, o[m])
            for s in SETUPS:
                _add(setups, f"{s}|{t}", o[m & k[s].to_numpy()])
    return {"setups": setups, "baseline": baseline}
