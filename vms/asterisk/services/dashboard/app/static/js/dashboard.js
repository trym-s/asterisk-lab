// Shared polling helper: calls `render(data)` with the parsed JSON from
// `url` immediately, then again every `refreshMs`. In-page refresh only,
// no WebSocket / SSE.
function pollJson(url, refreshMs, render) {
  async function tick() {
    try {
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) throw new Error(`${url} -> HTTP ${res.status}`);
      render(await res.json());
    } catch (err) {
      console.error("dashboard poll failed", err);
    }
  }
  tick();
  return setInterval(tick, refreshMs);
}

function fmtMs(ms) {
  if (ms === null || ms === undefined) return "?";
  return `${Math.round(ms)} ms`;
}

function fmtUsd(usd) {
  if (usd === null || usd === undefined) return "?";
  return `$${usd.toFixed(4)}`;
}

function fmtTs(ts) {
  if (!ts) return "?";
  return new Date(ts * 1000).toLocaleString();
}
