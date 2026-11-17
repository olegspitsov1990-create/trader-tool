"""Kursdaten laden (Yahoo Finance) und auf abgeschlossene Kerzen beschränken."""
from __future__ import annotations

import io
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger(__name__)

# timeframe -> (Yahoo-Zeitraum, Yahoo-Intervall)
PERIODS = {"1h": ("730d", "1h"), "4h": ("730d", "1h"), "1d": ("5y", "1d")}
TF_DELTA = {"1h": timedelta(hours=1), "4h": timedelta(hours=4), "1d": timedelta(days=1)}
MARKET_TZ = {"stocks": "America/New_York", "crypto": "UTC"}

SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def load_sp500(cache_path: Path) -> pd.DataFrame:
    """S&P-500-Liste von Wikipedia; bei Fehler die zuletzt gespeicherte Liste."""
    try:
        html = requests.get(SP500_URL, headers={"User-Agent": "Mozilla/5.0 trader-tool"}, timeout=30).text
        table = pd.read_html(io.StringIO(html))[0]
        out = pd.DataFrame({
            "symbol": table["Symbol"].astype(str).str.replace(".", "-", regex=False),
            "name": table["Security"].astype(str),
            "sector": table["GICS Sector"].astype(str),
        })
        if len(out) < 400:
            raise ValueError(f"unerwartet kurze Liste ({len(out)})")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(cache_path, index=False)
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("S&P-500-Liste nicht abrufbar (%s) – nutze Cache", exc)
        if cache_path.exists():
            return pd.read_csv(cache_path)
        raise


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=str.lower)
    cols = ["open", "high", "low", "close", "volume"]
    if not set(cols).issubset(df.columns):
        return pd.DataFrame()
    df = df[cols].dropna(subset=["open", "high", "low", "close"])
    df["volume"] = df["volume"].fillna(0)
    return df[~df.index.duplicated(keep="last")].sort_index()


def _resample_4h(df: pd.DataFrame) -> pd.DataFrame:
    return df.resample("4h", origin="epoch", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna(subset=["open", "close"])


def download(symbols: list[str], timeframe: str, market: str, chunk: int = 100, retries: int = 3) -> dict[str, pd.DataFrame]:
    import yfinance as yf

    period, interval = PERIODS[timeframe]
    result: dict[str, pd.DataFrame] = {}
    for i in range(0, len(symbols), chunk):
        part = symbols[i:i + chunk]
        raw = None
        for attempt in range(retries):
            try:
                raw = yf.download(part, period=period, interval=interval, group_by="ticker",
                                  auto_adjust=True, threads=True, progress=False)
                break
            except Exception as exc:  # noqa: BLE001
                log.warning("Download-Fehler (%s), Versuch %d", exc, attempt + 1)
                time.sleep(5 * (attempt + 1))
        if raw is None or raw.empty:
            continue
        for sym in part:
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    if sym not in raw.columns.get_level_values(0):
                        continue
                    df = raw[sym]
                else:
                    df = raw
                df = _localize(_normalize(df.copy()), market)
                if timeframe == "4h":
                    df = _resample_4h(df)
                if len(df) > 50:
                    result[sym] = df
            except Exception as exc:  # noqa: BLE001
                log.warning("%s: %s", sym, exc)
    # Zweiter Versuch für fehlende Symbole (einzeln, ohne Parallelität)
    missing = [s for s in symbols if s not in result]
    if missing and len(missing) <= 50:
        for sym in missing:
            try:
                df = yf.download(sym, period=period, interval=interval, auto_adjust=True, threads=False, progress=False)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df = _localize(_normalize(df.copy()), market)
                if timeframe == "4h":
                    df = _resample_4h(df)
                if len(df) > 50:
                    result[sym] = df
            except Exception as exc:  # noqa: BLE001
                log.warning("%s (2. Versuch): %s", sym, exc)
    log.info("%s %s: %d/%d Symbole geladen", market, timeframe, len(result), len(symbols))
    return result


def _localize(df: pd.DataFrame, market: str) -> pd.DataFrame:
    if df.empty:
        return df
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is None:
        idx = idx.tz_localize(MARKET_TZ[market])
    df.index = idx
    return df


def closed_bars(df: pd.DataFrame, timeframe: str, market: str, now: datetime) -> pd.DataFrame:
    """Nur vollständig abgeschlossene Kerzen behalten, Index in UTC."""
    df = _localize(df.copy(), market)
    if market == "stocks" and timeframe == "1d":
        ny = df.index.tz_convert("America/New_York").normalize()
        end = ny + pd.Timedelta(hours=16, minutes=15)
    else:
        end = df.index + TF_DELTA[timeframe]
    df = df[end <= pd.Timestamp(now)]
    df.index = df.index.tz_convert("UTC")
    return df
