"""E-Mail-Versand der Signale (SMTP, Zugangsdaten aus Umgebungsvariablen)."""
from __future__ import annotations

import html
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)


def de_num(x: float, dec: int | None = None) -> str:
    if dec is None:
        dec = 0 if abs(x) >= 1000 else (2 if abs(x) >= 1 else 4)
    s = f"{x:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(x: float) -> str:
    return f"{x * 100:.0f} %"


def _action(s: dict) -> tuple[str, str, str]:
    if s["setup"] == "SQUEEZE":
        return ("⚡", "AUSBRUCH ERWARTET", "oben" if s["direction"] == "long" else "unten")
    if s["direction"] == "long":
        return ("📈", "KAUF", "oben")
    return ("📉", "VERKAUF", "unten")


def subject(signals: list[dict]) -> str:
    top = signals[0]
    emo, act, way = _action(top)
    head = f"{emo} {act} {top['symbol']} {top['tf']} – {pct(top['score'])} {way}"
    if len(signals) > 1:
        head += f" (+{len(signals) - 1} weitere)"
    return head


def _local_time(iso: str, tf: str) -> str:
    t = pd.Timestamp(iso).tz_convert("Europe/Berlin")
    return t.strftime("%d.%m.%Y") if tf == "1d" else t.strftime("%d.%m.%Y %H:%M")


def render(signals: list[dict], site_url: str, more: int) -> tuple[str, str]:
    text_lines, rows = [], []
    for s in signals:
        emo, act, way = _action(s)
        up, down = s["cond_up"], 1 - s["cond_up"]
        vol = f" · Volumen {de_num(s['vol_ratio'], 1)}×" if s.get("vol_ratio") else ""
        text_lines.append(
            f"{emo} {act} {s['symbol']} ({s.get('name', s['symbol'])}) {s['tf']} – {s['title']}\n"
            f"   Kurs {de_num(s['close'])} | Ausbruch ↑ {pct(up)} / ↓ {pct(down)} "
            f"(Basis {pct(s['base_up'])} ↑) | Ausbruch überhaupt: {pct(s['p_breakout'])} | n={s['n']}\n"
            f"   Marken: ↑ {de_num(s['level_up'])} / ↓ {de_num(s['level_down'])} | RSI {s['rsi']:.0f}{vol} | Trend {s['trend']}\n"
        )
        color = "#0a7d38" if s["direction"] == "long" else "#b3261e"
        rows.append(f"""
<tr><td style="padding:10px;border-bottom:1px solid #eee;vertical-align:top">
  <div style="font-size:16px;font-weight:600;color:{color}">{emo} {act} {html.escape(s['symbol'])}
    <span style="color:#555;font-weight:400"> {html.escape(s.get('name', ''))} · {s['tf']}</span></div>
  <div style="color:#333;margin:2px 0 6px">{html.escape(s['title'])} – {html.escape(s['label'])}
    <span style="color:#888">· Kerze {_local_time(s['bar_time'], s['tf'])}</span></div>
  <table style="border-collapse:collapse;font-size:13px"><tr>
    <td style="padding-right:16px">Kurs <b>{de_num(s['close'])}</b></td>
    <td style="padding-right:16px">Ausbruch ↑ <b>{pct(up)}</b> / ↓ <b>{pct(down)}</b></td>
    <td style="padding-right:16px">Basisrate ↑ {pct(s['base_up'])}</td>
    <td>Ausbruch überhaupt {pct(s['p_breakout'])} · n={s['n']}</td></tr>
  <tr><td style="padding-right:16px">Marke ↑ {de_num(s['level_up'])}</td>
    <td style="padding-right:16px">Marke ↓ {de_num(s['level_down'])}</td>
    <td style="padding-right:16px">RSI {s['rsi']:.0f}{vol}</td><td>Trend {s['trend']}</td></tr></table>
</td></tr>""")
    link = f'<p><a href="{html.escape(site_url)}">Alle Signale und Charts auf der Website</a></p>' if site_url else ""
    more_txt = f"<p>… und {more} weitere Signale auf der Website.</p>" if more else ""
    body = f"""<html><body style="font-family:Arial,Helvetica,sans-serif;color:#222;max-width:720px">
<h2 style="margin-bottom:4px">Trader Tool – neue Signale</h2>
<p style="color:#666;margin-top:0">„Ausbruch ↑/↓“ = historischer Anteil, in dem der Kurs nach diesem Setup zuerst die obere bzw. untere Marke
(±Ausbruchsabstand in ATR) innerhalb des Zeitfensters erreicht hat. Basisrate = derselbe Wert ohne Setup.</p>
<table style="border-collapse:collapse;width:100%">{''.join(rows)}</table>{more_txt}{link}
<p style="color:#999;font-size:11px">Statistische Auswertung historischer Daten, keine Anlageberatung.</p>
</body></html>"""
    text = "Trader Tool – neue Signale\n\n" + "\n".join(text_lines)
    if more:
        text += f"\n… und {more} weitere Signale auf der Website.\n"
    if site_url:
        text += f"\nWebsite: {site_url}\n"
    return text, body


def send(signals: list[dict], cfg: dict, root: Path, dry_run: bool = False) -> None:
    if not signals:
        log.info("Keine neuen Signale – keine E-Mail.")
        return
    limit = int(cfg["alerts"].get("max_signals_per_mail", 25))
    signals = sorted(signals, key=lambda s: (s["edge"], s["score"]), reverse=True)
    shown, more = signals[:limit], max(0, len(signals) - limit)
    subj = subject(signals)
    text, body = render(shown, cfg.get("site_url", ""), more)

    host = os.environ.get("SMTP_HOST")
    if dry_run or not host:
        out = root / "out"
        out.mkdir(exist_ok=True)
        (out / "last_email.html").write_text(body, encoding="utf-8")
        (out / "last_email.txt").write_text(subj + "\n\n" + text, encoding="utf-8")
        log.info("E-Mail nicht versendet (Testmodus/kein SMTP) – Vorschau in out/. Betreff: %s", subj)
        return

    msg = EmailMessage()
    msg["Subject"] = subj
    msg["From"] = os.environ.get("MAIL_FROM") or os.environ["SMTP_USER"]
    msg["To"] = os.environ["MAIL_TO"]
    msg.set_content(text)
    msg.add_alternative(body, subtype="html")
    port = int(os.environ.get("SMTP_PORT") or 465)
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=60) as s:
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=60) as s:
            s.starttls(context=ctx)
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
            s.send_message(msg)
    log.info("E-Mail versendet: %s", subj)
