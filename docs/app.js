"use strict";

const GROUPS = { crypto: "Krypto", stocks: "Aktien" };
const data = { signals: [], stats: {}, status: {}, overview: {} };
const ov = { q: "", sort: "edge", dir: -1, limit: 100 };
let chart = null;
const live = { on: false, local: false, data: { crypto: {}, stocks: {} }, ws: null };

const $ = (s) => document.querySelector(s);
const pct = (x) => (x == null ? "–" : Math.round(x * 100) + " %");
const pct1 = (x) => (x == null ? "–" : (x > 0 ? "+" : "") + (x * 100).toLocaleString("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + " %");
const num = (x) => x == null ? "–" : x.toLocaleString("de-DE", { maximumFractionDigits: Math.abs(x) >= 1000 ? 0 : Math.abs(x) >= 1 ? 2 : 4 });
const dec = (x, d = 1) => x == null ? "–" : x.toLocaleString("de-DE", { minimumFractionDigits: d, maximumFractionDigits: d });
const pts = (e) => e == null ? "–" : (e > 0 ? "+" : "") + Math.round(e * 100) + " Pkt.";
const cls = (x) => x > 0 ? "pos" : x < 0 ? "neg" : "";
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const when = (iso, tf) => {
  const d = new Date(iso);
  return tf === "1d" ? d.toLocaleDateString("de-DE") : d.toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" });
};
const chartFile = (sym, tf) => `${sym.replace("/", "-").replace("^", "")}_${tf}.json`;

async function getJSON(url, fallback) {
  try { const r = await fetch(url + "?v=" + Date.now()); return r.ok ? await r.json() : fallback; }
  catch { return fallback; }
}

async function load() {
  data.signals = [];
  for (const g of Object.keys(GROUPS)) {
    const [sig, st, stat, o] = await Promise.all([
      getJSON(`data/${g}/signals.json`, []), getJSON(`data/${g}/stats.json`, {}),
      getJSON(`data/${g}/status.json`, null), getJSON(`data/${g}/overview.json`, {}),
    ]);
    data.signals.push(...sig);
    data.stats[g] = st;
    data.status[g] = stat;
    data.overview[g] = o;
  }
  data.signals.sort((a, b) => b.bar_time.localeCompare(a.bar_time));
  renderStatus();
  setupOverviewControls();
  render();
}

function renderStatus() {
  const fresh = live.on && live.data.updated && (Date.now() - new Date(live.data.updated)) < 180000;
  const dot = live.on ? `<span class="livedot ${fresh ? "on" : ""}" title="${live.local ? "Live-Kurse vom PC (Binance + Alpaca)" : "Live-Kurse Krypto direkt von Binance"}">● Live</span> ` : "";
  $("#status").innerHTML = dot + (Object.entries(data.status).filter(([, s]) => s)
    .map(([g, s]) => `${GROUPS[g]}: ${new Date(s.updated).toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" })}`)
    .join(" · ") || "Noch keine Daten");
}

/* ---------------- Live-Kurse ---------------- */

async function pollLive() {
  try {
    const r = await fetch("api/live?v=" + Date.now());
    if (!r.ok) throw new Error();
    live.data = await r.json();
    live.on = live.local = true;
  } catch {
    if (live.local) { live.on = false; }
    return false;
  }
  renderStatus();
  if (!$("#tab-overview").classList.contains("hidden")) renderOverview();
  return true;
}

function binanceInBrowser() {
  // Auf GitHub Pages (ohne PC-Server): Krypto-Kurse direkt von Binance im Browser
  const syms = Object.values(data.overview.crypto || {})[0]?.map((r) => r.symbol).filter((x) => x.endsWith("USDT")) || [];
  if (!syms.length || live.ws) return;
  const url = "wss://stream.binance.com:9443/stream?streams=" + syms.map((x) => x.toLowerCase() + "@miniTicker").join("/");
  live.ws = new WebSocket(url);
  live.ws.onmessage = (e) => {
    const d = JSON.parse(e.data).data;
    live.data.crypto[d.s] = { p: parseFloat(d.c), t: new Date(d.E).toISOString() };
    live.data.updated = new Date().toISOString();
    live.on = true;
  };
  live.ws.onclose = () => { live.ws = null; setTimeout(binanceInBrowser, 5000); };
  if (live.timer) return;
  live.timer = setInterval(() => { renderStatus(); if ($("#o-group").value === "crypto" && !$("#tab-overview").classList.contains("hidden")) renderOverview(); }, 3000);
}

async function checkForNewData() {
  for (const g of Object.keys(GROUPS)) {
    const st = await getJSON(`data/${g}/status.json`, null);
    if (st && st.updated !== data.status[g]?.updated) { await load(); return; }
  }
}

function liveRow(r, g) {
  const src = live.data[g]?.[r.symbol];
  if (!src || src.p == null || !r.close) return r;
  const atr = r.atr_pct * r.close;
  const hh = r.dist_hh != null ? r.close + r.dist_hh * atr : null;
  const ll = r.dist_ll != null ? r.close - r.dist_ll * atr : null;
  return { ...r, live: src.p, liveChg: src.p / r.close - 1,
    dist_hh: hh != null ? (hh - src.p) / atr : null, dist_ll: ll != null ? (src.p - ll) / atr : null };
}

/* ---------------- Marktübersicht ---------------- */

function setupOverviewControls() {
  const g = $("#o-group").value;
  const tfs = Object.keys(data.overview[g] || {});
  const prevTf = $("#o-tf").value;
  $("#o-tf").innerHTML = tfs.map((t) => `<option value="${t}">${t === "1d" ? "Tageskerzen" : t + "-Kerzen"}</option>`).join("");
  if (tfs.includes(prevTf)) $("#o-tf").value = prevTf;
  else if (tfs.includes("1d") && g === "stocks") $("#o-tf").value = "1d";
  const rows = currentRows();
  const sectors = [...new Set(rows.map((r) => r.sector).filter(Boolean))].sort();
  $("#o-sector").innerHTML = `<option value="">Alle Sektoren</option>` + sectors.map((s) => `<option>${esc(s)}</option>`).join("");
  $("#o-sector").classList.toggle("hidden", !sectors.length);
}

function currentRows() {
  const g = $("#o-group").value;
  return ((data.overview[g] || {})[$("#o-tf").value] || []).map((r) => liveRow(r, g));
}

function quickFilter(r) {
  switch (ov.q) {
    case "setup": return r.setups.length > 0;
    case "edge": return r.edge >= 0.05;
    case "squeeze": return r.squeeze_len > 0;
    case "nearhigh": return r.dist_hh != null && r.dist_hh <= 0.5;
    case "nearlow": return r.dist_ll != null && r.dist_ll <= 0.5;
    case "oversold": return r.rsi != null && r.rsi < 30;
    case "overbought": return r.rsi != null && r.rsi > 70;
    default: return true;
  }
}

const SORT = {
  symbol: (r) => r.symbol, close: (r) => r.live ?? r.close, chg: (r) => r.liveChg ?? r.chg, chg20: (r) => r.chg20, trend: (r) => r.trend,
  rsi: (r) => r.rsi, squeeze_len: (r) => r.squeeze_len, dist_hh: (r) => r.dist_hh, dist_ll: (r) => r.dist_ll,
  vol_ratio: (r) => r.vol_ratio, setups: (r) => r.setups.length, edge: (r) => r.edge,
  prob: (r) => r.direction === "short" ? 1 - r.cond_up : r.cond_up,
};

function kpis(rows) {
  if (!rows.length) return "";
  const n = rows.length;
  const up = rows.filter((r) => r.trend === "auf").length;
  const above50 = rows.filter((r) => r.above_ema50).length;
  const sq = rows.filter((r) => r.squeeze_len > 0).length;
  const bo = (name) => rows.filter((r) => r.setups.some((s) => s.setup === name)).length;
  const adv = rows.filter((r) => (r.liveChg ?? r.chg) > 0).length;
  const avgRsi = rows.reduce((a, r) => a + (r.rsi || 0), 0) / n;
  const k = (label, value, sub, c = "") => `<div class="kpi"><div class="kpi-l">${label}</div><div class="kpi-v ${c}">${value}</div><div class="kpi-s">${sub}</div></div>`;
  return [
    k("Über EMA 200", pct(up / n), `${up} von ${n} im Aufwärtstrend`, up / n >= 0.5 ? "pos" : "neg"),
    k("Über EMA 50", pct(above50 / n), "kurzfristige Stärke", above50 / n >= 0.5 ? "pos" : "neg"),
    k("Steigend / fallend", `${adv} / ${n - adv}`, rows.some((r) => r.live != null) ? "laufende Kerze (live)" : "letzte Kerze", adv >= n - adv ? "pos" : "neg"),
    k("Ø RSI", dec(avgRsi, 0), avgRsi > 60 ? "eher überkauft" : avgRsi < 40 ? "eher überverkauft" : "neutral"),
    k("Im Squeeze", sq, "Ausbruch baut sich auf"),
    k("Ausbrüche ↑ / ↓", `${bo("AUSBRUCH_OBEN")} / ${bo("AUSBRUCH_UNTEN")}`, "letzte Kerze"),
  ].join("");
}

function renderOverview() {
  const all = currentRows();
  const sector = $("#o-sector").value, q = $("#o-search").value.trim().toLowerCase();
  let rows = all.filter((r) => (!sector || r.sector === sector) && quickFilter(r) &&
    (!q || r.symbol.toLowerCase().includes(q) || (r.name || "").toLowerCase().includes(q)));
  const key = SORT[ov.sort];
  rows.sort((a, b) => {
    const x = key(a), y = key(b);
    if (x == null) return 1; if (y == null) return -1;
    return (x > y ? 1 : x < y ? -1 : 0) * ov.dir;
  });
  $("#o-kpis").innerHTML = kpis(all.filter((r) => !sector || r.sector === sector));
  if (!all.length) { $("#o-table").innerHTML = `<div class="empty">Noch keine Übersicht – sie entsteht beim nächsten Lauf.</div>`; return; }

  const th = (k, label, numCls = true, title = "") => `<th class="${numCls ? "num " : ""}sortable${ov.sort === k ? " sorted" : ""}" data-sort="${k}" title="${title}">${label}${ov.sort === k ? (ov.dir > 0 ? " ▲" : " ▼") : ""}</th>`;
  const shown = rows.slice(0, ov.limit);
  const tf = $("#o-tf").value, g = $("#o-group").value;
  $("#o-table").innerHTML = `<div class="count">${rows.length} von ${all.length} Symbolen · Stand ${all[0] ? when(all[0].bar_time, tf) : ""}</div>
  <div class="table-wrap"><table class="ov"><thead><tr>
    ${th("symbol", "Symbol", false)}${th("close", rows.some((r) => r.live != null) ? "Kurs (live)" : "Kurs")}${th("chg", rows.some((r) => r.live != null) ? "Kerze (live)" : "Kerze")}${th("chg20", "20 Kerzen")}${th("trend", "Trend", false)}
    ${th("rsi", "RSI")}${th("squeeze_len", "Squeeze", true, "Anzahl Kerzen im Bollinger-Squeeze")}
    ${th("dist_hh", "→ Hoch", true, "Abstand zum 20er-Hoch in ATR")}${th("dist_ll", "→ Tief", true, "Abstand zum 20er-Tief in ATR")}
    ${th("vol_ratio", "Volumen")}${th("setups", "Setups", false)}${th("prob", "Wahrsch.", true, "Historische Wahrscheinlichkeit in Setup-Richtung (ohne Setup: Basisrate ↑)")}${th("edge", "Vorteil")}
  </tr></thead><tbody>${shown.map((r) => `
    <tr class="row" data-chart="${g}|${esc(r.symbol)}|${tf}">
      <td><b>${esc(r.symbol)}</b><div class="sub">${esc(r.name)}</div></td>
      <td class="num">${r.live != null ? `<b>${num(r.live)}</b>` : num(r.close)}</td>
      <td class="num ${cls(r.liveChg ?? r.chg)}">${pct1(r.liveChg ?? r.chg)}</td>
      <td class="num ${cls(r.chg20)}">${pct1(r.chg20)}</td>
      <td class="${r.trend === "auf" ? "pos" : "neg"}">${r.trend === "auf" ? "↗ auf" : "↘ ab"}</td>
      <td class="num ${r.rsi > 70 ? "neg" : r.rsi < 30 ? "pos" : ""}">${dec(r.rsi, 0)}</td>
      <td class="num">${r.squeeze_len ? `<span class="sq">${r.squeeze_len}</span>` : "–"}</td>
      <td class="num">${r.dist_hh != null && r.dist_hh < 0 ? '<span class="pos">darüber</span>' : dec(r.dist_hh)}</td>
      <td class="num">${r.dist_ll != null && r.dist_ll < 0 ? '<span class="neg">darunter</span>' : dec(r.dist_ll)}</td>
      <td class="num">${r.vol_ratio != null ? dec(r.vol_ratio) + "×" : "–"}</td>
      <td>${r.setups.map((s) => `<span class="tag ${s.direction}" title="${esc(s.title)}: Richtung ↑ ${pct(s.cond_up)}, Vorteil ${pts(s.edge)}, n=${s.n}">${esc(s.title)}</span>`).join(" ") || '<span class="sub">–</span>'}</td>
      <td class="num">${!r.setups.length ? `<span class="sub">↑ ${pct(r.cond_up)}</span>` : r.direction === "short" ? `<span class="neg">↓ ${pct(1 - r.cond_up)}</span>` : `<span class="pos">↑ ${pct(r.cond_up)}</span>`}</td>
      <td class="num ${r.setups.length ? cls(r.edge) : ""}">${r.setups.length ? pts(r.edge) : "–"}</td>
    </tr>`).join("")}</tbody></table></div>
  ${rows.length > ov.limit ? `<button id="o-more" class="more">Weitere ${Math.min(100, rows.length - ov.limit)} anzeigen</button>` : ""}`;
}

/* ---------------- Signale / Verlauf / Statistik ---------------- */

function filtered() {
  const g = $("#f-group").value, dir = $("#f-dir").value, q = $("#f-search").value.trim().toLowerCase();
  return data.signals.filter((s) => (!g || s.group === g) && (!dir || s.direction === dir) &&
    (!q || s.symbol.toLowerCase().includes(q) || (s.name || "").toLowerCase().includes(q)));
}

function card(s) {
  const up = s.cond_up, down = 1 - s.cond_up;
  const action = s.setup === "SQUEEZE" ? "Ausbruch erwartet " + (s.direction === "long" ? "↑" : "↓")
    : s.direction === "long" ? "Kauf" : "Verkauf";
  return `<div class="card" data-signal="${esc(s.id)}">
    <div class="top"><div><span class="sym">${esc(s.symbol)}</span> <span class="name">${esc(s.name)} · ${s.tf}</span></div>
      <span class="badge ${s.direction}">${action}</span></div>
    <div class="setup">${esc(s.title)} <span class="name">· ${when(s.bar_time, s.tf)}</span></div>
    <div class="bar"><div class="u" style="width:${up * 100}%"></div><div class="d" style="width:${down * 100}%"></div></div>
    <div class="probs"><span>Ausbruch ↑ <b class="u">${pct(up)}</b></span><span>Basis ${pct(s.base_up)} ↑</span><span>↓ <b class="d">${pct(down)}</b></span></div>
    <div class="meta"><span>Kurs ${num(s.close)}</span><span>↑ ${num(s.level_up)} / ↓ ${num(s.level_down)}</span>
      <span>Vorteil ${pts(s.edge)}</span><span>n=${s.n}</span><span>RSI ${Math.round(s.rsi)}</span>
      <span>Trend ${s.trend}</span>${s.outcome ? `<span class="${s.hit ? "pos" : "neg"}">Ergebnis: ${s.outcome}</span>` : ""}</div>
  </div>`;
}

function renderSignals() {
  const open = filtered().filter((s) => s.outcome == null).slice(0, 200);
  $("#tab-signals").innerHTML = open.length ? `<div class="grid">${open.map(card).join("")}</div>`
    : `<div class="empty">Aktuell keine offenen Signale. Kandidaten ohne Alarm findest du in der Marktübersicht.</div>`;
}

function renderHistory() {
  const rows = filtered().slice(0, 500);
  if (!rows.length) { $("#tab-history").innerHTML = `<div class="empty">Noch kein Verlauf.</div>`; return; }
  $("#tab-history").innerHTML = `<div class="table-wrap"><table><thead><tr><th>Kerze</th><th>Symbol</th><th>TF</th><th>Setup</th><th>Richtung</th>
    <th class="num">Wahrsch.</th><th class="num">Kurs</th><th>Ergebnis</th></tr></thead><tbody>${rows.map((s) => `
    <tr class="row" data-signal="${esc(s.id)}"><td>${when(s.bar_time, s.tf)}</td><td><b>${esc(s.symbol)}</b></td><td>${s.tf}</td>
    <td>${esc(s.title)}</td><td class="${s.direction === "long" ? "pos" : "neg"}">${s.direction === "long" ? "↑" : "↓"}</td>
    <td class="num">${pct(s.score)}</td><td class="num">${num(s.close)}</td>
    <td class="${s.outcome == null ? "" : s.hit ? "pos" : "neg"}">${s.outcome == null ? "offen" : esc(s.outcome) + (s.hit ? " ✓" : " ✗")}</td></tr>`).join("")}
    </tbody></table></div>`;
}

function renderStats() {
  const gSel = $("#f-group").value;
  let html = "";
  for (const [g, byTf] of Object.entries(data.stats)) {
    if (gSel && g !== gSel) continue;
    const live = data.status[g]?.live || {};
    for (const [tf, st] of Object.entries(byTf)) {
      const b = st.baseline || {};
      html += `<h3>${GROUPS[g]} · ${tf} <span class="name">Basis: Ausbruch ↑ ${pct(b.auf?.cond_up)} im Aufwärtstrend,
        ${pct(b.ab?.cond_up)} im Abwärtstrend</span></h3>
        <div class="table-wrap"><table><thead><tr><th>Setup</th><th>Trend</th><th class="num">Fälle</th><th class="num">Ausbruch ↑</th>
        <th class="num">Ausbruch ↓</th><th class="num">Richtung ↑</th><th class="num">Vorteil ggü. Basis</th><th class="num">Live-Treffer</th></tr></thead><tbody>`;
      const rows = st.setups.filter((r) => r.n > 0).sort((a, b) => a.setup.localeCompare(b.setup) || a.trend.localeCompare(b.trend));
      for (const r of rows) {
        const base = b[r.trend]?.cond_up;
        let edge = r.cond_up != null && base != null ? r.cond_up - base : null;
        let edgeDir = "";
        if (edge != null && r.direction === "short") edge = -edge;
        if (edge != null && r.direction === "neutral") { edgeDir = edge >= 0 ? " ↑" : " ↓"; edge = Math.abs(edge); }
        const lv = live[`${tf}|${r.setup}`];
        html += `<tr><td>${esc(r.title)}</td><td>${r.trend}</td><td class="num">${r.n}</td>
          <td class="num">${pct(r.p_up)}</td><td class="num">${pct(r.p_down)}</td><td class="num">${pct(r.cond_up)}</td>
          <td class="num ${cls(edge)}">${pts(edge)}${edgeDir}</td>
          <td class="num">${lv ? `${pct(lv.hits / lv.n)} (${lv.n})` : "–"}</td></tr>`;
      }
      html += `</tbody></table></div>`;
    }
  }
  $("#tab-stats").innerHTML = html || `<div class="empty">Noch keine Statistik.</div>`;
}

function render() { renderOverview(); renderSignals(); renderHistory(); renderStats(); }

/* ---------------- Chart ---------------- */

const RANGE_SEC = { "1D": 86400, "5D": 5 * 86400, "1M": 31 * 86400, "3M": 92 * 86400, "6M": 183 * 86400,
  "1Y": 366 * 86400, "2Y": 731 * 86400, "5Y": 1827 * 86400 };
const DEFAULT_INT = { "1D": "5m", "5D": "15m", "1M": "1h", "3M": "1d", "6M": "1d", "YTD": "1d", "1Y": "1d",
  "2Y": "1w", "5Y": "1w", "MAX": "1M" };
const INT_MS = { "1m": 6e4, "5m": 3e5, "15m": 9e5, "1h": 36e5, "4h": 144e5, "1d": 864e5, "1w": 6048e5, "1M": 26298e5 };
const cv = { group: null, symbol: null, signal: null, interval: "1d", range: "1Y", timer: null, req: 0 };

function rangeStart(range, lastSec) {
  if (range === "MAX") return null;
  if (range === "YTD") return Date.UTC(new Date().getUTCFullYear(), 0, 1) / 1000;
  return lastSec - RANGE_SEC[range];
}

async function binanceDirect(symbol, interval, range) {
  // ohne PC-Server: Krypto-Kerzen direkt im Browser von Binance
  const step = INT_MS[interval], now = Date.now();
  const days = range === "MAX" ? null : range === "YTD" ? (now - Date.UTC(new Date().getUTCFullYear(), 0, 1)) / 864e5 : RANGE_SEC[range] / 86400;
  let start = days == null ? 15e11 : now - days * 864e5 - 220 * step;
  start = Math.max(start, now - 5000 * step);
  const rows = [];
  for (const base of ["https://data-api.binance.vision", "https://api.binance.com"]) {
    try {
      let s = start;
      rows.length = 0;
      while (s < now) {
        const r = await fetch(`${base}/api/v3/klines?symbol=${symbol}&interval=${interval}&startTime=${Math.floor(s)}&limit=1000`);
        if (!r.ok) throw new Error();
        const b = await r.json();
        if (!b.length) break;
        rows.push(...b);
        s = b[b.length - 1][0] + 1;
        if (b.length < 1000) break;
      }
      break;
    } catch { /* nächste Quelle */ }
  }
  if (!rows.length) return { error: "Binance nicht erreichbar" };
  return { source: "Binance", time: rows.map((x) => x[0] / 1000), open: rows.map((x) => +x[1]), high: rows.map((x) => +x[2]),
    low: rows.map((x) => +x[3]), close: rows.map((x) => +x[4]), volume: rows.map((x) => +x[5]) };
}

function resample(c, interval) {
  if (interval === "1d") return c;
  const out = { source: c.source, time: [], open: [], high: [], low: [], close: [], volume: [] };
  let key = null;
  c.time.forEach((t, i) => {
    const d = new Date(t * 1000);
    const k = interval === "1M" ? Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1) / 1000
      : (Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()) / 1000) - ((d.getUTCDay() + 6) % 7) * 86400;
    if (k !== key) {
      key = k;
      out.time.push(k); out.open.push(c.open[i]); out.high.push(c.high[i]); out.low.push(c.low[i]);
      out.close.push(c.close[i]); out.volume.push(c.volume?.[i] || 0);
    } else {
      const n = out.time.length - 1;
      out.high[n] = Math.max(out.high[n], c.high[i]); out.low[n] = Math.min(out.low[n], c.low[i]);
      out.close[n] = c.close[i]; out.volume[n] += c.volume?.[i] || 0;
    }
  });
  return out;
}

async function fetchCandles(group, symbol, interval, range) {
  if (live.local) {
    try {
      const r = await fetch(`api/candles?group=${group}&symbol=${encodeURIComponent(symbol)}&interval=${interval}&range=${range}`);
      const j = await r.json();
      if (r.ok && j.time?.length) return j;
    } catch { /* Fallback */ }
  }
  if (group === "crypto") return binanceDirect(symbol, interval, range);
  const c = await getJSON(`data/${group}/charts/${chartFile(symbol, "1d")}`, null);
  if (!c) return { error: "Keine Chartdaten vorhanden." };
  if (!["1d", "1w", "1M"].includes(interval)) return { error: "Intraday-Charts für Aktien gibt es im Live-Modus auf dem PC (http://localhost:8080)." };
  c.source = "gespeicherte Tagesdaten";
  return resample(c, interval);
}

function sma(values, n) {
  const out = new Array(values.length).fill(null);
  let sum = 0;
  values.forEach((v, i) => { sum += v; if (i >= n) sum -= values[i - n]; if (i >= n - 1) out[i] = sum / n; });
  return out;
}

const localShift = (t) => t - new Date(t * 1000).getTimezoneOffset() * 60;  // Achse in deutscher Ortszeit

function fmtBarTime(t, interval) {
  const d = new Date(t * 1000);
  if (["1d", "1w", "1M"].includes(interval)) return d.toLocaleDateString("de-DE", { timeZone: "UTC", day: "2-digit", month: "short", year: "numeric" });
  return d.toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" });
}

async function openChart(group, symbol, tf, signal) {
  Object.assign(cv, { group, symbol, signal });
  if (signal || tf) {
    const t = signal?.tf || tf;
    cv.interval = t; cv.range = t === "1d" ? "1Y" : t === "4h" ? "3M" : "1M";
  }
  const row = ((data.overview[group] || {})[tf || "1d"] || []).find((r) => r.symbol === symbol)
    || Object.values(data.overview[group] || {}).flat().find((r) => r.symbol === symbol);
  $("#modal-title").innerHTML = `${esc(symbol)} <span class="name">${esc(signal?.name || row?.name || "")}${row?.sector ? " · " + esc(row.sector) : ""}</span>`;
  const info = [];
  if (row) {
    info.push(`Trend <b class="${row.trend === "auf" ? "pos" : "neg"}">${row.trend}</b>`, `RSI <b>${dec(row.rsi, 0)}</b>`,
      `Squeeze <b>${row.squeeze_len || "–"}</b>`, `→ 20er-Hoch <b>${dec(row.dist_hh)}</b> ATR`, `→ 20er-Tief <b>${dec(row.dist_ll)}</b> ATR`);
    for (const s of row.setups) info.push(`<span class="tag ${s.direction}">${esc(s.title)}</span> ${s.direction === "short" ? "↓ " + pct(1 - s.cond_up) : "↑ " + pct(s.cond_up)}, Vorteil ${pts(s.edge)} (n=${s.n})`);
  }
  if (signal) info.push(`Signal: <b>${esc(signal.title)}</b> · Marke ↑ ${num(signal.level_up)} / ↓ ${num(signal.level_down)}`);
  $("#modal-info").innerHTML = info.map((x) => `<span>${x}</span>`).join("");
  $("#modal").classList.remove("hidden");
  history.replaceState(null, "", `#chart=${group}|${encodeURIComponent(symbol)}|${tf || signal?.tf || "1d"}`);
  await drawChart(true);
}

async function drawChart(fresh) {
  document.querySelectorAll("#c-int button").forEach((b) => b.classList.toggle("active", b.dataset.i === cv.interval));
  document.querySelectorAll("#c-rng button").forEach((b) => b.classList.toggle("active", b.dataset.r === cv.range));
  const req = ++cv.req;
  const el = $("#chart");
  if (fresh) { if (chart) { chart.remove(); chart = null; } el.innerHTML = `<div class="empty">Lade Kerzen …</div>`; }
  const c = await fetchCandles(cv.group, cv.symbol, cv.interval, cv.range);
  if (req !== cv.req) return;  // inzwischen andere Auswahl
  if (!c || c.error || !c.time?.length) {
    if (chart) { chart.remove(); chart = null; }
    el.innerHTML = `<div class="empty">${esc(c?.error || "Keine Daten.")}</div>`; $("#c-legend").innerHTML = ""; return;
  }
  if (!window.LightweightCharts) { el.innerHTML = `<div class="empty">Chart-Bibliothek nicht geladen (Internet?).</div>`; return; }
  const intraday = !["1d", "1w", "1M"].includes(cv.interval);
  const T = c.time.map((t) => (intraday ? localShift(t) : t));
  const bars = T.map((t, i) => ({ time: t, open: c.open[i], high: c.high[i], low: c.low[i], close: c.close[i] }));
  const smas = { 20: sma(c.close, 20), 50: sma(c.close, 50), 200: sma(c.close, 200) };
  const keepRange = !fresh && chart ? chart.timeScale().getVisibleLogicalRange() : null;

  if (fresh || !chart) {
    el.innerHTML = "";
    if (chart) chart.remove();
    const dark = matchMedia("(prefers-color-scheme: dark)").matches;
    chart = LightweightCharts.createChart(el, {
      autoSize: true,
      layout: { background: { color: "transparent" }, textColor: dark ? "#9aa3b2" : "#4b5563", fontSize: 11 },
      grid: { vertLines: { color: dark ? "#232833" : "#f0f2f5" }, horzLines: { color: dark ? "#232833" : "#f0f2f5" } },
      rightPriceScale: { scaleMargins: { top: 0.06, bottom: 0.22 } },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
      timeScale: { timeVisible: intraday, secondsVisible: false, rightOffset: 4 },
      localization: { locale: "de-DE", priceFormatter: (p) => num(p) },
    });
    chart._s = {
      candles: chart.addCandlestickSeries({ upColor: "#16a34a", downColor: "#dc2626", borderVisible: false,
        wickUpColor: "#16a34a", wickDownColor: "#dc2626" }),
      vol: chart.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "vol", lastValueVisible: false, priceLineVisible: false }),
      s20: chart.addLineSeries({ color: "#a855f7", lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }),
      s50: chart.addLineSeries({ color: "#f59e0b", lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }),
      s200: chart.addLineSeries({ color: "#a16207", lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }),
    };
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    chart.subscribeCrosshairMove((p) => legend(p && p.time != null ? chart._idx.get(p.time) : null));
  }
  const S = chart._s;
  S.candles.setData(bars);
  S.vol.setData(T.map((t, i) => ({ time: t, value: c.volume[i] || 0,
    color: c.close[i] >= c.open[i] ? "rgba(22,163,74,.35)" : "rgba(220,38,38,.35)" })));
  for (const n of [20, 50, 200]) S["s" + n].setData(T.map((t, i) => ({ time: t, value: smas[n][i] })).filter((x) => x.value != null));
  chart._idx = new Map(T.map((t, i) => [t, i]));
  chart._c = c; chart._smas = smas;

  // Signal-Pfeile, wenn die Zeiteinheit zum Signal passt
  const marks = data.signals.filter((s) => s.group === cv.group && s.symbol === cv.symbol && s.tf === cv.interval)
    .map((s) => { const t = new Date(s.bar_time).getTime() / 1000; return { time: intraday ? localShift(t) : t, s }; })
    .filter((m) => chart._idx.has(m.time))
    .map(({ time, s }) => ({ time, position: s.direction === "long" ? "belowBar" : "aboveBar", color: s.direction === "long" ? "#16a34a" : "#dc2626",
      shape: s.direction === "long" ? "arrowUp" : "arrowDown", text: s.title }));
  S.candles.setMarkers(marks.sort((a, b) => a.time - b.time));

  if (keepRange) chart.timeScale().setVisibleLogicalRange(keepRange);
  else {
    const last = T[T.length - 1], from = rangeStart(cv.range, c.time[c.time.length - 1]);
    if (from == null) chart.timeScale().fitContent();
    else chart.timeScale().setVisibleRange({ from: intraday ? localShift(from) : from, to: last });
  }
  legend(null);

  clearInterval(cv.timer);
  if (live.local || cv.group === "crypto") {  // laufende Kerze aktualisieren
    cv.timer = setInterval(() => { if (!$("#modal").classList.contains("hidden")) drawChart(false); }, intraday ? 15000 : 60000);
  }
}

function legend(i) {
  const c = chart?._c;
  if (!c) return;
  if (i == null) i = c.time.length - 1;
  const prev = i > 0 ? c.close[i - 1] : c.open[i];
  const chg = c.close[i] / prev - 1;
  const f = (x) => num(x);
  const sm = (n, color) => `<span style="color:${color}">SMA ${n} ${chart._smas[n][i] != null ? f(chart._smas[n][i]) : "–"}</span>`;
  $("#c-legend").innerHTML = `<b>${fmtBarTime(c.time[i], cv.interval)}</b>
    <span>O <b>${f(c.open[i])}</b></span><span>H <b>${f(c.high[i])}</b></span><span>L <b>${f(c.low[i])}</b></span>
    <span>C <b class="${cls(chg)}">${f(c.close[i])}</b></span><span class="${cls(chg)}">${pct1(chg)}</span>
    <span>Vol <b>${compact(c.volume[i])}</b></span>${sm(20, "#a855f7")}${sm(50, "#f59e0b")}${sm(200, "#a16207")}
    <span class="src">${esc(c.source || "")}</span>`;
}

const compact = (v) => v == null ? "–" : Intl.NumberFormat("de-DE", { notation: "compact", maximumFractionDigits: 2 }).format(v);

function closeChart() { clearInterval(cv.timer); cv.req++; history.replaceState(null, "", location.pathname + location.search); $("#modal").classList.add("hidden"); if (chart) { chart.remove(); chart = null; } }

$("#c-int").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-i]"); if (!b) return;
  cv.interval = b.dataset.i;
  drawChart(true);
});
$("#c-rng").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-r]"); if (!b) return;
  cv.range = b.dataset.r; cv.interval = DEFAULT_INT[cv.range];
  drawChart(true);
});

/* ---------------- Events ---------------- */

document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === b));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("hidden", p.id !== "tab-" + b.dataset.tab));
  $("#sig-filters").classList.toggle("hidden", b.dataset.tab === "overview");
}));
["#f-group", "#f-dir", "#f-search"].forEach((s) => $(s).addEventListener("input", () => { renderSignals(); renderHistory(); renderStats(); }));
$("#o-group").addEventListener("input", () => { ov.limit = 100; setupOverviewControls(); renderOverview(); });
["#o-tf", "#o-sector", "#o-search"].forEach((s) => $(s).addEventListener("input", () => { ov.limit = 100; renderOverview(); }));
$("#o-chips").addEventListener("click", (e) => {
  const b = e.target.closest(".chip");
  if (!b) return;
  ov.q = b.dataset.q; ov.limit = 100;
  document.querySelectorAll(".chip").forEach((x) => x.classList.toggle("active", x === b));
  renderOverview();
});
document.addEventListener("click", (e) => {
  const th = e.target.closest("th[data-sort]");
  if (th) {
    const k = th.dataset.sort;
    if (ov.sort === k) ov.dir *= -1; else { ov.sort = k; ov.dir = k === "symbol" || k === "dist_hh" || k === "dist_ll" ? 1 : -1; }
    renderOverview();
    return;
  }
  if (e.target.id === "o-more") { ov.limit += 100; renderOverview(); return; }
  const r = e.target.closest("[data-chart]");
  if (r) { const [g, sym, tf] = r.dataset.chart.split("|"); openChart(g, sym, tf, null); return; }
  const s = e.target.closest("[data-signal]");
  if (s) { const sig = data.signals.find((x) => x.id === s.dataset.signal); if (sig) openChart(sig.group, sig.symbol, sig.tf, sig); }
});
$("#modal-close").addEventListener("click", closeChart);
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeChart(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeChart(); });

(async () => {
  await load();
  if (await pollLive()) {
    setInterval(pollLive, 5000);          // lokaler PC-Server: Livekurse alle 5 s
  } else {
    binanceInBrowser();                    // GitHub Pages: Krypto live direkt von Binance
  }
  setInterval(checkForNewData, 30000);     // nach jeder Auswertung automatisch neu laden
  const m = location.hash.match(/^#chart=([^|]+)\|([^|]+)\|(\w+)/);
  if (m) openChart(m[1], decodeURIComponent(m[2]), m[3], null);
})();
