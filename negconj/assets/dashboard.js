/* Shared by the U.S. Code dashboards (negconn, 1225b); inlined into each page when it is built
   (negconj.dashboard): data-file loading, text helpers, citations, review storage, CSV export,
   keyboard navigation. */
const PENDING = {};
// Data files are plain scripts, so a page also works opened from disk.
function loadScript(src) {
  if (PENDING[src]) return PENDING[src];
  return PENDING[src] = new Promise((ok, fail) => { const s = document.createElement("script"); s.src = src; s.onload = ok;
    s.onerror = () => { delete PENDING[src]; fail(new Error("could not load " + src)); }; document.head.appendChild(s); });
}
const BRK = { "-LRB-": "(", "-RRB-": ")", "-LSB-": "[", "-RSB-": "]", "-LCB-": "{", "-RCB-": "}" };
const word = w => BRK[w] || w;
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const $ = id => document.getElementById(id);

/* ---------- citation helpers ---------- */
function citation(ident) {
  const m = /^\/us\/usc\/t(\w+)\/s([^/]+)((?:\/[^/]+)*)$/.exec(ident);
  if (!m) return ident || "(no identifier)";
  const sub = m[3].split("/").filter(Boolean).map(x => `(${x})`).join("");
  const t = m[1].replace(/^0+/, "");
  return `${t.endsWith("a") ? t.slice(0, -1) + " U.S.C. App." : t + " U.S.C."} § ${m[2]}${sub}`;
}
function liiUrl(ident) {
  const m = /^\/us\/usc\/t(\d+)\/s([^/]+)/.exec(ident);
  return m ? `https://www.law.cornell.edu/uscode/text/${+m[1]}/${m[2].replace(/–/g, "-")}` : null;
}
// Title order: 1, 2, …, 5, 5a, …; then citations in numeric order.
function natKey(t) { const m = /^(\d+)(.*)$/.exec(t); return m ? [+m[1], m[2]] : [1e9, t]; }
function cmpTitle(a, b) { const x = natKey(a), y = natKey(b); return x[0] - y[0] || (x[1] < y[1] ? -1 : x[1] > y[1] ? 1 : 0); }
const cmpIdent = (a, b) => a.localeCompare(b, undefined, { numeric: true });
function titleOptions(titles) {
  return [...titles].sort(cmpTitle).map(t => `<option value="${esc(t)}">Title ${esc(t.replace(/^0+/, ""))}</option>`).join("");
}

/* ---------- text width (for drawing) ---------- */
let measureCtx;
function tw(s, font = "12px 'IBM Plex Mono', monospace") { measureCtx = measureCtx || document.createElement("canvas").getContext("2d"); measureCtx.font = font; return measureCtx.measureText(s).width; }

/* ---------- reviews, kept in this browser's localStorage ---------- */
const REVIEW_LABEL = { yes: "✓ yes", no: "✗ no", unsure: "? unsure" };
function loadReviews(key, legacy = () => ({})) {
  try { return JSON.parse(localStorage.getItem(key) || "null") || legacy(); } catch (e) { return {}; }
}
function storeReviews(key, reviews) { try { localStorage.setItem(key, JSON.stringify(reviews)); } catch (e) { /* storage unavailable */ } }
const csvCell = s => `"${String(s ?? "").replace(/"/g, '""')}"`;
function downloadCsv(name, lines) {
  const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
  a.download = name; document.body.appendChild(a); a.click(); a.remove();
}

/* ---------- keyboard: j/k (or arrows) step through the list, 1/2/3 set the review mark ---------- */
function bindKeys(step, mark) {
  document.addEventListener("keydown", e => {
    if (e.target.closest("input, textarea, select") || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "j" || e.key === "ArrowDown") { step(1); e.preventDefault(); }
    else if (e.key === "k" || e.key === "ArrowUp") { step(-1); e.preventDefault(); }
    else if (e.key === "1") mark("yes"); else if (e.key === "2") mark("no"); else if (e.key === "3") mark("unsure");
  });
}
