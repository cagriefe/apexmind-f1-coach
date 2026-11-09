"use strict";
const $ = (s) => document.querySelector(s);
const fmtLap = (ms) => {
  if (ms == null || ms <= 0) return "–";
  ms = Math.round(ms);
  return Math.floor(ms / 60000) + ":" + ((ms % 60000) / 1000).toFixed(3).padStart(6, "0");
};
const LEDS = 15;
const rev = $("#rev");
for (let i = 0; i < LEDS; i++) rev.append(document.createElement("i"));
const leds = [...rev.children];
const ledClass = (i) => (i < 5 ? "g" : i < 10 ? "r" : "b");

let lastStateAt = 0;
function setLive(on) {
  const c = $("#c-live");
  c.textContent = on ? "LIVE" : "Waiting";
  c.classList.toggle("on", on);
}

function updateRev(pct, gear) {
  const n = Math.round((Math.max(0, Math.min(100, pct || 0)) / 100) * LEDS);
  leds.forEach((el, i) => { el.className = i < n ? "on " + ledClass(i) : ""; });
  rev.classList.toggle("flash", n >= LEDS && gear > 0);
}

// Tyre colours follow the coach's own thresholds (cold below 70 C, hot above 112 C inner).
function tyreClass(inner) {
  if (inner == null) return "";
  return inner < 70 ? "cold" : inner < 95 ? "ok" : inner <= 112 ? "warm" : "hot";
}

function update(st) {
  lastStateAt = performance.now();
  setLive(true);
  $("#speed").textContent = st.speed;
  $("#gear").textContent = st.gear < 0 ? "R" : st.gear === 0 ? "N" : st.gear;
  updateRev(st.rev, st.gear);
  const thr = st.throttle * 100, brk = st.brake * 100;
  $("#p-thr").style.height = thr + "%"; $("#p-brk").style.height = brk + "%";
  $("#p-thr-v").textContent = Math.round(thr); $("#p-brk-v").textContent = Math.round(brk);
  $("#steer").style.left = 50 + Math.max(-1, Math.min(1, st.steer)) * 50 + "%";

  const gx = st.g_lat ?? 0, gy = st.g_long ?? 0;
  const dot = $("#g-dot");
  dot.setAttribute("cx", Math.max(-46, Math.min(46, gx * 15)));
  dot.setAttribute("cy", Math.max(-46, Math.min(46, -gy * 15)));
  $("#g-v").textContent = Math.hypot(gx, gy).toFixed(1);

  $("#lap-n").textContent = st.lap ?? "–";
  $("#sector").textContent = st.sector == null ? "–" : st.sector + 1;
  $("#laptime").textContent = st.lap_ms ? fmtLap(st.lap_ms) : "0:00.000";
  $("#last").textContent = fmtLap(st.last_ms);
  $("#best").textContent = fmtLap(st.best_ms);
  const d = $("#delta");
  if (st.delta_ms == null) { d.textContent = "–"; d.className = "delta"; }
  else {
    d.textContent = (st.delta_ms > 0 ? "+" : "−") + (Math.abs(st.delta_ms) / 1000).toFixed(3);
    d.className = "delta " + (Math.abs(st.delta_ms) < 5 ? "" : st.delta_ms > 0 ? "up" : "down");
  }

  const pos = $("#c-pos");
  pos.hidden = !st.pos; pos.textContent = "P" + st.pos;
  $("#c-lap").textContent = "L" + (st.lap ?? "–") + (st.total_laps ? "/" + st.total_laps : "");
  $("#c-drs").hidden = !st.drs;
  const flag = $("#c-flag");
  const f = st.spin ? ["SPIN", "bad"] : st.invalid ? ["INVALID", "bad"] : st.pit ? ["PIT", "warn"] : null;
  flag.hidden = !f;
  if (f) { flag.textContent = f[0]; flag.className = "pill " + f[1]; }

  document.querySelectorAll(".tyre").forEach((el) => {
    const i = +el.dataset.i;
    const inner = st.tyre_in ? st.tyre_in[i] : null;
    const surf = st.tyre_surf ? st.tyre_surf[i] : null;
    const wear = st.wear ? st.wear[i] : null;
    el.className = "tyre " + tyreClass(inner);
    el.firstChild.textContent = inner == null ? "–" : inner + "°";
    el.lastChild.textContent = [surf == null ? "" : "S" + surf, wear == null ? "" : wear + "%"].filter(Boolean).join(" · ");
  });
}

let callTimer = 0;
function advice(ev, quiet) {
  if (quiet) return;
  const t = ev.text || "";
  const el = $("#call");
  $("#call-t").textContent = t;
  const k = ev.kind || "";
  const cls = /brake|ease/i.test(k) || /^brake/i.test(t) ? "brake"
    : /gas|full/i.test(k) || /^(gas|full)/i.test(t) ? "gas"
    : /lockup|slide|limits|wide|spin|damage/i.test(k) ? "warn" : "fresh";
  el.className = "call fresh " + (cls === "fresh" ? "" : cls);
  clearTimeout(callTimer);
  callTimer = setTimeout(() => { el.className = "call"; }, 2500);
}

/* ------------------------------------------------------------------ music */
function renderMedia(m) {
  const box = $("#music");
  box.hidden = !(m && m.available);
  if (box.hidden) return;
  $("#m-title").textContent = m.player && m.title ? m.title : m.player ? "Nothing playing" : "No music app running";
  $("#m-artist").textContent = m.player ? (m.artist ? m.artist + " · " : "") + m.player : "Open Music or Spotify on this computer";
  $("#m-play").textContent = m.playing ? "\u23F8" : "\u25B6";
  $("#m-vol").style.width = (m.volume ?? 0) + "%";
}
document.querySelectorAll(".m-ctl button").forEach((b) => b.addEventListener("click", async () => {
  try { await fetch("api/media/" + b.dataset.a, { method: "POST" }); } catch { /* offline */ }
}));

/* ------------------------------------------------------------- plumbing */
async function init() {
  let snap = null;
  try { const r = await fetch("api/live", { cache: "no-store" }); if (r.ok) snap = await r.json(); } catch { /* static host */ }
  if (snap && snap.live) {
    if (snap.state && snap.state.speed != null) update(snap.state);
    renderMedia(snap.media);
  }
  const es = new EventSource("events");
  es.addEventListener("snapshot", (e) => { const s = JSON.parse(e.data); renderMedia(s.media); });
  es.addEventListener("state", (e) => update(JSON.parse(e.data)));
  es.addEventListener("advice", (e) => advice(JSON.parse(e.data)));
  es.addEventListener("media", (e) => renderMedia(JSON.parse(e.data)));
  es.onerror = () => setLive(false);
  setInterval(() => { if (performance.now() - lastStateAt > 3000) setLive(false); }, 1000);
}
init();

// Keep the screen awake while driving (where the browser allows it).
let wake = null;
async function keepAwake() {
  try { if ("wakeLock" in navigator) wake = await navigator.wakeLock.request("screen"); } catch { /* denied */ }
}
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") keepAwake(); });
document.addEventListener("click", keepAwake, { once: true });
keepAwake();

// iPhone Safari has no fullscreen API for pages: "Add to Home Screen" gives the full-screen app.
const fs = $("#btn-full");
if (document.documentElement.requestFullscreen) fs.addEventListener("click", () => document.documentElement.requestFullscreen().catch(() => {}));
else fs.hidden = true;
