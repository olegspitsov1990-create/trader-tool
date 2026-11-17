"""Ein Überwachungslauf für eine Gruppe (crypto oder stocks).

Aufruf:  python run.py --group crypto            # normal (sendet E-Mail, wenn SMTP gesetzt)
         python run.py --group stocks --dry-run  # nur Vorschau in out/, keine E-Mail
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import yaml

from trader import data, indicators, notify, overview, setups, site, state as st, stats

ROOT = Path(__file__).resolve().parent
log = logging.getLogger("trader")


def run(group: str, dry_run: bool = False, root: Path = ROOT,
        provider: Callable | None = None, universe: Callable | None = None,
        now: datetime | None = None) -> list[dict]:
    cfg = yaml.safe_load((root / "config" / "config.yaml").read_text(encoding="utf-8"))
    gcfg, acfg, alcfg = cfg["groups"][group], cfg["analysis"], cfg["alerts"]
    market = gcfg["market"]
    now = now or datetime.now(timezone.utc)

    if gcfg.get("universe") == "sp500":
        meta = universe() if universe else data.load_sp500(root / "state" / "sp500.csv")
        symbols, names = meta["symbol"].tolist(), dict(zip(meta["symbol"], meta["name"]))
        sectors = dict(zip(meta["symbol"], meta["sector"])) if "sector" in meta else {}
    else:
        symbols, names = list(gcfg["symbols"]), dict(gcfg.get("names") or {})
        sectors = {}

    state_path = root / "state" / f"{group}.json"
    state = st.load(state_path)
    signals = site.load_signals(root, group)
    new_signals: list[dict] = []
    stats_by_tf: dict = {}
    overview_by_tf: dict = {}
    status: dict = {"group": group, "symbols": len(symbols), "timeframes": {}}

    for tf in gcfg["timeframes"]:
        frames = provider(symbols, tf, market) if provider else data.download(symbols, tf, market)
        prepared = {}
        for sym, df in frames.items():
            df = data.closed_bars(df, tf, market, now)
            if len(df) < stats.WARMUP + 50:
                continue
            d = setups.detect(indicators.add_indicators(df, acfg), acfg)
            d["outcome"], d["known"] = stats.label_outcomes(d, acfg)
            prepared[sym] = d
        if not prepared:
            log.warning("%s %s: keine verwertbaren Daten", group, tf)
            continue

        table = stats.aggregate(prepared)
        stats_by_tf[tf] = table
        resolved = site.resolve(signals, prepared, tf)

        tf_new = []
        for sym, d in prepared.items():
            key = f"{sym}|{tf}"
            last_t = d.index[-1]
            if not st.is_new_bar(state, key, last_t):
                continue
            for sig in setups.signals_on_last_bar(d, sym, tf, group, table, acfg, alcfg):
                if st.in_cooldown(state, sig, int(alcfg.get("cooldown_bars", 5))):
                    continue
                sig["name"] = names.get(sym, sym)
                st.mark(state, sig)
                tf_new.append(sig)
            st.set_bar(state, key, last_t)

        signals.extend(tf_new)
        new_signals.extend(tf_new)
        rows = []
        for sym, d in prepared.items():
            site.write_chart(root, group, sym, tf, d, signals)
            try:
                rows.append(overview.row(d, sym, names.get(sym, sym), sectors.get(sym), table))
            except Exception as exc:  # noqa: BLE001
                log.warning("Übersicht %s %s: %s", sym, tf, exc)
        overview_by_tf[tf] = rows
        last_bar = max(d.index[-1] for d in prepared.values())
        status["timeframes"][tf] = {"symbols": len(prepared), "last_bar": last_bar.isoformat(),
                                    "new_signals": len(tf_new), "resolved": resolved}
        log.info("%s %s: %d Symbole, %d neue Signale, %d Ergebnisse nachgetragen",
                 group, tf, len(prepared), len(tf_new), resolved)

    site.save(root, group, signals, stats_by_tf, status, overview_by_tf)
    st.save(state_path, state)
    notify.send(new_signals, cfg, root, dry_run=dry_run)
    return new_signals


def main() -> None:
    p = argparse.ArgumentParser(description="Trader Tool – Überwachungslauf")
    p.add_argument("--group", required=True, choices=["crypto", "stocks"])
    p.add_argument("--dry-run", action="store_true", help="keine E-Mail senden, Vorschau in out/")
    p.add_argument("--test-mail", action="store_true", help="nur eine Test-E-Mail senden")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if a.test_mail:
        cfg = yaml.safe_load((ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))
        notify.send_test(cfg)
        return
    run(a.group, dry_run=a.dry_run)


if __name__ == "__main__":
    main()
