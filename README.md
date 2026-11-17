# Trader Tool

Überwacht **BTCUSDT, ETHUSDT (1h / 4h / 1D, Binance)** und **alle S&P-500-Aktien (1D)**, erkennt Kauf-/Verkaufs-Setups auf der
zuletzt abgeschlossenen Kerze, berechnet aus der Historie die **Wahrscheinlichkeit eines Ausbruchs nach oben bzw. unten**
und schickt Alarme per **E-Mail**. Alle Signale, Charts und Trefferquoten stehen auf einer **Website** (GitHub Pages).
Läuft komplett kostenlos auf GitHub.

## So funktioniert es
- **Chart-Ansicht (Klick auf ein Symbol):** Kerzen mit Volumen, SMA 20/50/200, O/H/L/C unter dem Mauszeiger,
  Zeiteinheiten 1 Min bis Monatlich, Zeiträume 1 Tag bis Max – inkl. laufender Kerze (Krypto: Binance, Aktien: Yahoo).
  Intraday-Charts für Aktien gibt es im Live-Modus auf dem PC; Krypto-Charts auch auf GitHub Pages.
- **Website:** Marktübersicht aller überwachten Symbole (Trend, RSI, Squeeze, Abstand zu Hoch/Tief, aktive Setups,
  Wahrscheinlichkeit, Chart per Klick), dazu Signale, Verlauf und Statistik.
- **Datenhaltung:** Kurs-/Chartdaten und der Zustand liegen im Zweig `data`, der bei jedem Lauf überschrieben wird –
  so wächst das Repository nicht an. Der Zweig `main` enthält nur den Programmcode.
- **Krypto:** stündlich (Minute 7). Aktien: werktags 21:35 UTC, nach US-Börsenschluss.
- **Setups:** Ausbruch über Hoch/unter Tief mit Volumen, Bollinger-Squeeze, RSI-Umkehr, EMA-20/50-Kreuz, Engulfing.
- **Wahrscheinlichkeit:** Für jedes Setup (getrennt nach Auf-/Abwärtstrend über EMA 200) wird über die gesamte Historie
  aller Symbole gezählt, wie oft der Kurs danach **zuerst +1,5 ATR oder zuerst −1,5 ATR** innerhalb von 10 Kerzen erreicht hat.
  Ein Alarm geht nur raus, wenn die Richtungswahrscheinlichkeit ≥ 57 % ist und mindestens 30 historische Fälle vorliegen.
  Zum Vergleich wird immer die **Basisrate** (ohne Setup) angezeigt – nur ein Abstand zur Basis ist ein echter Vorteil.
- **Live-Kontrolle:** Jedes verschickte Signal wird nach Ablauf automatisch bewertet („Verlauf“ und „Live-Treffer“ auf der Website).
- Alle Schwellwerte stehen in `config/config.yaml`.

## Live-Modus auf dem PC (empfohlen)

Kurse höchstens Sekunden hinter TradingView: Krypto kommt live von **Binance** (gleiche Kerzen wie `BINANCE:BTCUSDT`),
jede 1h/4h/1D-Kerze wird Sekunden nach Schluss ausgewertet. Aktien-Livekurse kommen jede Minute über **Alpaca**
(kostenloser Datenfeed IEX); die Tageskerze wird 2 Minuten nach US-Börsenschluss ausgewertet.
Die Website läuft lokal unter **http://localhost:8080** – im Heimnetz auch auf dem Handy (Adresse steht im Fenster).

### Einrichtung (einmalig, ca. 15 Minuten)
1. **Python 3.12** von https://www.python.org/downloads/ installieren – beim Installieren **„Add python.exe to PATH“** anhaken.
2. **Programm herunterladen:** auf GitHub **Code → Download ZIP**, entpacken, z. B. nach `C:\Trader-Tool`.
3. **Alpaca-Konto (kostenlos):** https://alpaca.markets → registrieren → im Dashboard **API Keys → Generate**.
   Key-ID und Secret notieren (das Secret wird nur einmal angezeigt).
4. **Doppelklick auf `Trader-Tool starten.bat`.** Beim ersten Start öffnet sich die Datei `.env` im Editor:
   E-Mail-Daten (wie bei GitHub) und die beiden Alpaca-Schlüssel eintragen, speichern, Editor schließen, Taste drücken.
5. Das Fenster bleibt offen und zeigt, was passiert. Die Website öffnet sich automatisch.

### Dauerbetrieb
- **Automatisch mit Windows starten:** `Win+R` → `shell:startup` → Verknüpfung zu `Trader-Tool starten.bat` hineinlegen.
- **Ruhezustand verhindern:** Einstellungen → System → Netzbetrieb → „Bildschirm aus“ beliebig, aber **„Ruhezustand: Nie“**.
- **Updates:** neue ZIP herunterladen und über den Ordner entpacken (`.env` und Daten bleiben erhalten).
- Ist der PC aus, laufen keine Auswertungen. Beim nächsten Start wird die jeweils letzte Kerze nachgeholt.

## Betrieb über GitHub (Alternative ohne PC)
Der Zeitplan auf GitHub ist abgeschaltet, damit keine doppelten E-Mails kommen. Manuelle Läufe und die Test-E-Mail
gehen weiter über **Actions → Run workflow**. Zum Reaktivieren die `schedule`-Zeilen in
`.github/workflows/monitor.yml` wieder einkommentieren (Verzögerung dann ca. 5–60 Minuten).

## Einrichtung GitHub & Website (ca. 15 Minuten)

### 1. Repository anlegen
1. Auf [github.com](https://github.com) anmelden → **New repository** → Name z. B. `trader-tool`.
2. Sichtbarkeit **Public** (GitHub Pages und unbegrenzte Actions-Minuten sind nur bei öffentlichen Repos kostenlos;
   die Website ist dann für jeden mit dem Link sichtbar – E-Mail-Zugangsdaten bleiben trotzdem geheim).
3. **Add file → Upload files** → den gesamten Inhalt dieses Ordners hochladen (inkl. des Ordners `.github`) → **Commit**.
   Tipp: Der Ordner `.github` ist im Explorer/Finder evtl. ausgeblendet. Alternativ mit GitHub Desktop oder `git push` hochladen.

### 2. E-Mail-Zugang (Gmail)
1. Im Google-Konto **2-Faktor-Authentifizierung** aktivieren.
2. [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) → App-Passwort „Trader Tool“ erstellen (16 Zeichen).

### 3. Secrets hinterlegen
Im Repo: **Settings → Secrets and variables → Actions → New repository secret**:

| Name | Wert (Gmail) |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `465` |
| `SMTP_USER` | deine Gmail-Adresse |
| `SMTP_PASS` | das App-Passwort |
| `MAIL_TO` | Empfänger (mehrere mit Komma trennen) |
| `MAIL_FROM` | optional, sonst = `SMTP_USER` |

Andere Anbieter (z. B. Brevo, GMX, web.de) funktionieren genauso – Host/Port vom Anbieter übernehmen (Port 587 = STARTTLS).

### 4. Website aktivieren
**Settings → Pages → Build and deployment → Source: „GitHub Actions“.**
Die Adresse lautet danach `https://DEIN-NAME.github.io/trader-tool/`. Trage sie in `config/config.yaml` bei `site_url` ein,
dann ist sie in jeder E-Mail verlinkt.

### 5. Erster Start
**Actions → „Trader Tool – Überwachung“ → Run workflow**
- erst `stocks` mit **Testlauf ohne E-Mail** (dauert ca. 3–6 Minuten), dann `crypto` ohne Testlauf.
- Ab dann läuft alles automatisch nach Zeitplan.

## Handy
Die Betreffzeile enthält das Wichtigste, z. B. `📈 KAUF NVDA 1d – 61 % oben (+3 weitere)`, und ist damit schon in der
Push-Benachrichtigung lesbar. Tipp: In der Mail-App für die Absenderadresse eine eigene Benachrichtigung/ein Label anlegen.

## Anpassen
- Symbole/Zeiteinheiten: `config/config.yaml` → `groups`
- Weniger/mehr Alarme: `alerts.min_probability`, `alerts.min_samples`
- Ausbruchsdefinition: `analysis.barrier_atr`, `analysis.horizon_bars`

## Lokal testen
```bash
pip install -r requirements.txt
python tests/test_offline.py            # mit Testdaten, ohne Internet
python run.py --group crypto --dry-run  # echte Daten, E-Mail-Vorschau in out/
```

## Grenzen
- Kursdaten von Yahoo Finance (inoffiziell, kann ausfallen oder verzögert sein). Für Ausfallsicherheit später eine bezahlte API.
- GitHub startet geplante Läufe manchmal einige Minuten verspätet.
- Die Wahrscheinlichkeiten sind historische Häufigkeiten, keine Garantie. **Keine Anlageberatung.**
