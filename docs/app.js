"use strict";

const GROUPS = { crypto: "Krypto", stocks: "Aktien" };
const data = { signals: [], stats: {}, status: {} };
let chart = null;

const $ = (s) => document.querySelector(s);
const pct = (x) => (x == null ? "–" : Math.round(x * 100) + " %");
const num = (x) => x == null ? "–" : x.toLocaleString("de-DE", { maximumFractionDigits: Math.abs(x) >= 1000 ? 0 : Math.abs(x) >= 1 ? 2 : 4 });
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const when = (iso, tf) => {
  const d = new Date(iso);
  return tf === "1d" ? d.toLocaleDateString("de-DE") : d.toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" });
};

async function getJSON(url, fallback) {
  try { const r = await fetch(url + "?v=" + Date.now()); return r.ok ? await r.json() : fallback; }
  catch { return fallback; }
}

async function load() {
  for (const g of Object.keys(GROUPS)) {
    const [sig, st, stat] = await Promise.all([
      getJSON(`data/${g}/signals.json`, []), getJSON(`data/${g}/stats.json`, {}), getJSON(`data/${g}/status.json`, null),
    ]);
    data.signals.push(...sig);
    data.stats[g] = st;
    data.status[g] = stat;
  }
  data.signals.sort((a, b) => b.bar_time.localeCompare(a.bar_time));
  $("#status").innerHTML = Object.entries(data.status).filter(([, s]) => s)
    .map(([g, s]) => `${GROUPS[g]}: ${new Date(s.updated).toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" })}`)
    .join(" · ") || "Noch keine Daten";
  render();
}

function filtered() {
  const g = $("#f-group").value, dir = $("#f-dir").value, q = $("#f-search").value.trim().toLowerCase();
  return data.signals.filter((s) => (!g || s.group === g) && (!dir || s.direction === dir) &&
    (!q || s.symbol.toLowerCase().includes(q) || (s.name || "").toLowerCase().includes(q)));
}

function card(s) {
  const up = s.cond_up, down = 1 - s.cond_up;
  const action = s.setup === "SQUEEZE" ? "Ausbruch erwartet " + (s.direction === "long" ? "↑" : "↓")
    : s.direction === "long" ? "Kauf" : "Verkauf";
  return `<div class="card" data-id="${esc(s.id)}">
    <div class="top"><div><span class="sym">${esc(s.symbol)}</span> <span class="name">${esc(s.name)} · ${s.tf}</span></div>
      <span class="badge ${s.direction}">${action}</span></div>
    <div class="setup">${esc(s.title)} <span class="name">· ${when(s.bar_time, s.tf)}</span></div>
    <div class="bar"><div class="u" style="width:${up * 100}%"></div><div class="d" style="width:${down * 100}%"></div></div>
    <div class="probs"><span>Ausbruch ↑ <b class="u">${pct(up)}</b></span><span>Basis ${pct(s.base_up)} ↑</span><span>↓ <b class="d">${pct(down)}</b></span></div>
    <div class="meta"><span>Kurs ${num(s.close)}</span><span>↑ ${num(s.level_up)} / ↓ ${num(s.level_down)}</span>
      <span>Ausbruch überhaupt ${pct(s.p_breakout)}</span><span>n=${s.n}</span><span>RSI ${Math.round(s.rsi)}</span>
      <span>Trend ${s.trend}</span>${s.outcome ? `<span class="${s.hit ? "pos" : "neg"}">Ergebnis: ${s.outcome}</span>` : ""}</div>
  </div>`;
}

function renderSignals() {
  const open = filtered().filter((s) => s.outcome == null).slice(0, 200);
  $("#tab-signals").innerHTML = open.length ? `<div class="grid">${open.map(card).join("")}</div>`
    : `<div class="empty">Aktuell keine offenen Signale.</div>`;
}

function renderHistory() {
  const rows = filtered().slice(0, 500);
  if (!rows.length) { $("#tab-history").innerHTML = `<div class="empty">Noch kein Verlauf.</div>`; return; }
  $("#tab-history").innerHTML = `<table><thead><tr><th>Kerze</th><th>Symbol</th><th>TF</th><th>Setup</th><th>Richtung</th>
    <th class="num">Wahrsch.</th><th class="num">Kurs</th><th>Ergebnis</th></tr></thead><tbody>${rows.map((s) => `
    <tr class="row" data-id="${esc(s.id)}"><td>${when(s.bar_time, s.tf)}</td><td><b>${esc(s.symbol)}</b></td><td>${s.tf}</td>
    <td>${esc(s.title)}</td><td class="${s.direction === "long" ? "pos" : "neg"}">${s.direction === "long" ? "↑" : "↓"}</td>
    <td class="num">${pct(s.score)}</td><td class="num">${num(s.close)}</td>
    <td class="${s.outcome == null ? "" : s.hit ? "pos" : "neg"}">${s.outcome == null ? "offen" : esc(s.outcome) + (s.hit ? " ✓" : " ✗")}</td></tr>`).join("")}
    </tbody></table>`;
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
        <table><thead><tr><th>Setup</th><th>Trend</th><th class="num">Fälle</th><th class="num">Ausbruch ↑</th>
        <th class="num">Ausbruch ↓</th><th class="num">Richtung ↑</th><th class="num">ggü. Basis</th><th class="num">Live-Treffer</th></tr></thead><tbody>`;
      const rows = st.setups.filter((r) => r.n > 0).sort((a, b) => a.setup.localeCompare(b.setup) || a.trend.localeCompare(b.trend));
      for (const r of rows) {
        const base = b[r.trend]?.cond_up;
        const edge = r.cond_up != null && base != null ? r.cond_up - base : null;
        const lv = live[`${tf}|${r.setup}`];
        html += `<tr><td>${esc(r.title)}</td><td>${r.trend}</td><td class="num">${r.n}</td>
          <td class="num">${pct(r.p_up)}</td><td class="num">${pct(r.p_down)}</td><td class="num">${pct(r.cond_up)}</td>
          <td class="num ${edge > 0 ? "pos" : edge < 0 ? "neg" : ""}">${edge == null ? "–" : (edge > 0 ? "+" : "") + Math.round(edge * 100) + " Pkt."}</td>
          <td class="num">${lv ? `${pct(lv.hits / lv.n)} (${lv.n})` : "–"}</td></tr>`;
      }
      html += `</tbody></table>`;
    }
  }
  $("#tab-stats").innerHTML = html || `<div class="empty">Noch keine Statistik.</div>`;
}

function render() { renderSignals(); renderHistory(); renderStats(); }

async function openChart(id) {
  const s = data.signals.find((x) => x.id === id);
  if (!s) return;
  const file = `${s.symbol.replace("/", "-").replace("^", "")}_${s.tf}.json`;
  const c = await getJSON(`data/${s.group}/charts/${file}`, null);
  $("#modal-title").textContent = `${s.symbol} · ${s.name} · ${s.tf}`;
  $("#modal").classList.remove("hidden");
  const el = $("#chart");
  el.innerHTML = "";
  if (!c || !window.LightweightCharts) { el.innerHTML = `<div class="empty">Kein Chart verfügbar.</div>`; return; }
  const dark = matchMedia("(prefers-color-scheme: dark)").matches;
  chart = LightweightCharts.createChart(el, {
    autoSize: true,
    layout: { background: { color: "transparent" }, textColor: dark ? "#9aa3b2" : "#4b5563" },
    grid: { vertLines: { color: dark ? "#2a303b" : "#eef0f3" }, horzLines: { color: dark ? "#2a303b" : "#eef0f3" } },
    timeScale: { timeVisible: s.tf !== "1d" }, localization: { locale: "de-DE" },
  });
  const candles = chart.addCandlestickSeries({ upColor: "#16a34a", downColor: "#dc2626", borderVisible: false,
    wickUpColor: "#16a34a", wickDownColor: "#dc2626" });
  candles.setData(c.time.map((t, i) => ({ time: t, open: c.open[i], high: c.high[i], low: c.low[i], close: c.close[i] })));
  for (const [key, color] of [["ema20", "#f59e0b"], ["ema50", "#3b82f6"], ["ema200", "#a855f7"]]) {
    chart.addLineSeries({ color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
      .setData(c.time.map((t, i) => ({ time: t, value: c[key][i] })).filter((p) => p.value != null));
  }
  candles.setMarkers(c.markers.map((m) => ({ time: m.time, position: m.direction === "long" ? "belowBar" : "aboveBar",
    color: m.direction === "long" ? "#16a34a" : "#dc2626", shape: m.direction === "long" ? "arrowUp" : "arrowDown", text: m.title }))
    .sort((a, b) => a.time - b.time));
  candles.createPriceLine({ price: s.level_up, color: "#16a34a", lineStyle: 2, title: "Marke ↑" });
  candles.createPriceLine({ price: s.level_down, color: "#dc2626", lineStyle: 2, title: "Marke ↓" });
  chart.timeScale().fitContent();
}

function closeChart() { $("#modal").classList.add("hidden"); if (chart) { chart.remove(); chart = null; } }

document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === b));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("hidden", p.id !== "tab-" + b.dataset.tab));
}));
["#f-group", "#f-dir", "#f-search"].forEach((s) => $(s).addEventListener("input", render));
document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-id]");
  if (t) openChart(t.dataset.id);
});
$("#modal-close").addEventListener("click", closeChart);
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeChart(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeChart(); });

load();
