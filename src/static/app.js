/* Dashboard logic: vanilla JS, polls the Flask API. */
const $ = (id) => document.getElementById(id);
let pendingId = null;

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  return r.json();
}

async function refreshMode() {
  const m = await api("/api/mode");
  const badge = $("mode-badge");
  badge.textContent = m.mode;
  badge.className = "badge " + m.mode.toLowerCase();
  $("gate-note").textContent = m.gate_reason +
    (m.live_armed ? ` — cap $${m.max_order_usd}/order.` : "");
  $("session-state").textContent = m.session_confirmed
    ? "session CONFIRMED for live orders" : "session not confirmed";
}

async function refreshWatchers() {
  const ws = await api("/api/watchers");
  $("watchers").innerHTML = ws.map(w =>
    `<div class="row"><span>${w.enabled ? "🟢" : "⚪"} <b>${w.name}</b>: ≥$${w.min_usd}, ` +
    `${Math.round(w.prob_min*100)}–${Math.round(w.prob_max*100)}%</span>` +
    `<button onclick="delWatcher('${w.name}')">Remove</button></div>`).join("")
    || '<span class="muted">none</span>';
  const s = await api("/api/watcher/state");
  $("watcher-state").textContent =
    `${s.running ? "🟢 running" : "⚪ stopped"} — ${s.polls} polls, ${s.alerts} alerts`;
}
async function delWatcher(name) {
  await api("/api/watchers/" + encodeURIComponent(name), { method: "DELETE" });
  refreshWatchers();
}

async function refreshAlerts() {
  const alerts = await api("/api/alerts?limit=20");
  $("alerts").innerHTML = alerts.map(a =>
    `<div class="alert"><div><b>$${a.size_usd.toLocaleString()}</b> ${a.side} ${a.outcome} @ ${(a.price*100).toFixed(1)}%<br>${a.market_title}</div>` +
    `<div class="meta">${a.watcher_name} · ${new Date(a.detected_at*1000).toLocaleTimeString()}</div>` +
    `<div class="actions">` +
    `<button onclick="follow('${a.tx_hash}','paper')">📄 Follow (paper)</button>` +
    `<button onclick="follow('${a.tx_hash}','live')">⚡ Follow (LIVE)</button>` +
    `</div></div>`).join("") || '<span class="muted">no alerts yet — start the watcher</span>';
}

async function refreshPositions() {
  const ps = await api("/api/positions");
  if (!ps.length) { $("positions").innerHTML = '<span class="muted">no paper positions</span>'; return; }
  $("positions").innerHTML = `<table><tr><th>#</th><th>Market</th><th>Side</th><th>Entry</th><th>Size</th><th>P&L</th><th></th></tr>` +
    ps.map(p => `<tr><td>${p.id}</td><td>${p.market_title.slice(0,40)}</td>` +
      `<td>${p.side} ${p.outcome}</td><td>${p.entry_price.toFixed(3)}</td><td>$${p.size_usd}</td>` +
      `<td class="${p.pnl_usd >= 0 ? "pos-pnl-pos" : "pos-pnl-neg"}">${p.pnl_usd == null ? "—" : "$" + p.pnl_usd.toFixed(2)}</td>` +
      `<td>${p.status === "open" ? `<button onclick="closePos(${p.id})">Close</button>` : p.status}</td></tr>`).join("") + "</table>";
}
async function closePos(id) {
  await api(`/api/positions/${id}/close`, { method: "POST" });
  refreshPositions();
}

async function follow(tx_hash, mode) {
  const r = await api("/api/follow", {
    method: "POST",
    body: JSON.stringify({ tx_hash, size_usd: 25, mode }),
  });
  if (!r.ok) { alert("Error: " + (r.error || "unknown")); return; }
  if (r.needs_confirmation) {
    pendingId = r.pending_id;
    $("confirm-text").textContent = r.preview.summary;
    $("confirm-modal").classList.remove("hidden");
    return;
  }
  alert(r.mode === "live" ? "⚡ LIVE order placed!" : `📄 Paper position #${r.position_id} opened`);
  refreshPositions();
}

$("btn-confirm-order").onclick = async () => {
  const r = await api(`/api/follow/confirm/${pendingId}`, { method: "POST" });
  $("confirm-modal").classList.add("hidden");
  alert(r.ok ? "⚡ LIVE order placed!" : "Error: " + r.error);
  pendingId = null;
};
$("btn-cancel-order").onclick = () => {
  $("confirm-modal").classList.add("hidden");
  pendingId = null;
};

$("btn-start").onclick = async () => { await api("/api/watcher/start", { method: "POST" }); refreshWatchers(); };
$("btn-stop").onclick = async () => { await api("/api/watcher/stop", { method: "POST" }); refreshWatchers(); };
$("btn-add-watcher").onclick = async () => {
  await api("/api/watchers", { method: "POST", body: JSON.stringify({
    name: $("w-name").value, min_usd: +$("w-min").value,
    prob_min: +$("w-pmin").value, prob_max: +$("w-pmax").value }) });
  refreshWatchers();
};
$("btn-confirm-session").onclick = async () => {
  if (!$("session-confirm").checked) { alert("Tick the checkbox first."); return; }
  const r = await api("/api/session/confirm", { method: "POST", body: JSON.stringify({ confirmed: true }) });
  alert(r.ok ? "Session confirmed for LIVE orders." : "Error: " + r.error);
  refreshMode();
};

setInterval(() => { refreshMode(); refreshAlerts(); refreshPositions(); refreshWatchers(); }, 5000);
refreshMode(); refreshAlerts(); refreshPositions(); refreshWatchers();
