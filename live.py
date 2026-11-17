"""Trader Tool – Live-Modus für den eigenen PC.

Startet:
  * eine lokale Website unter http://localhost:8080 (im Heimnetz auch über die IP des PCs erreichbar)
  * eine Live-Verbindung zu Binance: Kurse in Echtzeit, Auswertung jeder 1h/4h/1D-Kerze Sekunden nach Schluss
  * Aktien-Livekurse über Alpaca (jede Minute) und die Auswertung der Tageskerze kurz nach US-Börsenschluss
  * E-Mail-Alarme wie bisher

Start unter Windows: Doppelklick auf "Trader-Tool starten.bat"   ·   sonst: python live.py
Beenden: Fenster schließen oder Strg+C.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import threading
from datetime import datetime, time as dtime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

import run as runner
from trader import alpaca, data

ROOT = Path(__file__).resolve().parent
NY = ZoneInfo("America/New_York")
log = logging.getLogger("live")

LIVE: dict = {"updated": None, "crypto": {}, "stocks": {}, "binance": False, "alpaca": False}
RUN_LOCK = threading.Lock()


def load_env() -> None:
    """Zugangsdaten aus der Datei .env laden (Zeilen KEY=WERT)."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ---------------------------------------------------------------- lokale Website

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.split("?")[0] == "/api/live":
            body = json.dumps(LIVE).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):  # keine Zugriffsprotokolle im Fenster
        pass


def serve(port: int) -> None:
    httpd = ThreadingHTTPServer(("0.0.0.0", port), partial(Handler, directory=str(ROOT / "docs")))
    httpd.serve_forever()


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "IP-des-PCs"


# ---------------------------------------------------------------- Auswertung

def analyze(group: str) -> None:
    with RUN_LOCK:
        t0 = datetime.now()
        try:
            sigs = runner.run(group)
            log.info("Auswertung %s fertig in %.0f s – %d neue Signale", group,
                     (datetime.now() - t0).total_seconds(), len(sigs))
        except Exception:  # noqa: BLE001
            log.exception("Auswertung %s fehlgeschlagen", group)


# ---------------------------------------------------------------- Krypto (Binance)

async def crypto_stream(symbols: list[str], tfs: list[str]) -> None:
    import websockets

    streams = "/".join(f"{s.lower()}@kline_{i}" for s in symbols for i in ["1m", *tfs])
    url = f"wss://stream.binance.com:9443/stream?streams={streams}"
    pending: asyncio.Task | None = None

    async def delayed_run():
        await asyncio.sleep(3)  # REST-Daten der gerade geschlossenen Kerze abwarten
        await asyncio.to_thread(analyze, "crypto")

    while True:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                LIVE["binance"] = True
                log.info("Binance live verbunden (%s)", ", ".join(symbols))
                async for msg in ws:
                    k = json.loads(msg)["data"]["k"]
                    if k["i"] == "1m":
                        LIVE["crypto"][k["s"]] = {"p": float(k["c"]), "t": datetime.fromtimestamp(
                            k["T"] / 1000, timezone.utc).isoformat(timespec="seconds")}
                        LIVE["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    elif k["x"]:
                        log.info("Kerze geschlossen: %s %s – starte Auswertung", k["s"], k["i"])
                        if pending is None or pending.done():
                            pending = asyncio.create_task(delayed_run())
        except Exception as exc:  # noqa: BLE001
            LIVE["binance"] = False
            log.warning("Binance-Verbindung unterbrochen (%s) – neuer Versuch in 5 s", exc)
            await asyncio.sleep(5)


# ---------------------------------------------------------------- Aktien (Alpaca + Yahoo)

async def stocks_loop(cfg: dict) -> None:
    poll = int(cfg.get("live", {}).get("stocks_poll_seconds", 60))
    buffer_min = int(cfg["analysis"].get("stock_close_buffer_minutes", 2))
    symbols = data.load_sp500(ROOT / "state" / "sp500.csv")["symbol"].tolist()
    if not alpaca.configured():
        log.warning("Keine Alpaca-Zugangsdaten in .env – Aktien ohne Livekurse (Auswertung nach Börsenschluss läuft trotzdem).")
    last_eval = None
    first = True
    while True:
        ny = datetime.now(NY)
        weekday = ny.weekday() < 5
        market_open = weekday and dtime(9, 30) <= ny.time() <= dtime(16, 0, 59)
        if alpaca.configured() and (market_open or first):
            try:
                snap = await asyncio.to_thread(alpaca.snapshots, symbols)
                LIVE["stocks"] = snap
                LIVE["alpaca"] = True
                LIVE["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            except Exception as exc:  # noqa: BLE001
                LIVE["alpaca"] = False
                log.warning("Alpaca: %s", exc)
        first = False
        if weekday and ny.time() >= dtime(16, buffer_min) and last_eval != ny.date():
            last_eval = ny.date()
            log.info("US-Börsenschluss – werte Tageskerze aus")
            await asyncio.to_thread(analyze, "stocks")
        await asyncio.sleep(poll if market_open else 30)


# ---------------------------------------------------------------- Start

async def main_async() -> None:
    cfg = yaml.safe_load((ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))
    port = int(cfg.get("live", {}).get("port", 8080))
    threading.Thread(target=serve, args=(port,), daemon=True).start()
    log.info("Website: http://localhost:%d   (im Heimnetz, z. B. Handy im WLAN: http://%s:%d)", port, local_ip(), port)

    # Startauswertung, damit die Website sofort aktuelle Daten hat (keine doppelten Mails dank Zustand)
    await asyncio.to_thread(analyze, "crypto")
    await asyncio.to_thread(analyze, "stocks")

    c = cfg["groups"]["crypto"]
    await asyncio.gather(crypto_stream(c["symbols"], c["timeframes"]), stocks_loop(cfg))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    for noisy in ("yfinance", "urllib3", "websockets", "peewee"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    load_env()
    print("=" * 70)
    print(" Trader Tool – Live-Modus läuft. Dieses Fenster bitte geöffnet lassen.")
    print("=" * 70)
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("Beendet.")


if __name__ == "__main__":
    main()
