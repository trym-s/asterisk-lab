// Shared polling helper: calls `render(data)` with parsed JSON from `url`
// immediately, then again every refresh interval. No WebSocket / SSE.
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

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function fmtMs(ms) {
  if (ms === null || ms === undefined) return "?";
  return `${Math.round(ms)} ms`;
}

function fmtUsd(usd) {
  if (usd === null || usd === undefined) return "?";
  return `$${Number(usd).toFixed(4)}`;
}

function fmtTs(ts) {
  if (!ts) return "?";
  return new Date(ts * 1000).toLocaleString();
}

function fmtShortTs(ts) {
  if (!ts) return "?";
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function fmtAgo(ts) {
  if (!ts) return "?";
  const seconds = Math.max(0, Math.round(Date.now() / 1000 - ts));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  return `${Math.round(seconds / 3600)}h ago`;
}

function fmtDuration(seconds) {
  const value = Number(seconds || 0);
  if (value < 3600) return `${Math.round(value / 60)}m`;
  if (value < 86400) return `${Math.round(value / 3600)}h`;
  return `${Math.round(value / 86400)}d`;
}

function shortId(value) {
  const text = String(value || "");
  return text.length > 22 ? `${text.slice(0, 10)}...${text.slice(-8)}` : text;
}

function laneColor(lane) {
  return {
    livekit: "#16a6c9",
    pipecat: "#d98f1f",
  }[String(lane || "").toLowerCase()] || "#64748b";
}

function laneBadge(lane) {
  const safe = escapeHtml(lane || "unknown");
  const key = safe.toLowerCase();
  return `<span class="lane-badge lane-${key}">${safe}</span>`;
}

function statusBadge(text, status) {
  return `<span class="status-badge status-${escapeHtml(status)}">${escapeHtml(text)}</span>`;
}

function transcriptBadges(call) {
  return [
    statusBadge(call.live_transcript ? "live STT" : "no live STT", call.live_transcript ? "up" : "muted"),
    statusBadge(call.batch_transcript ? "batch TXT" : "no batch TXT", call.batch_transcript ? "up" : "muted"),
  ].join(" ");
}

function chartDataset(label, data, color) {
  return {
    label,
    data,
    borderColor: color,
    backgroundColor: color,
    tension: 0.35,
    pointRadius: 2,
    pointHoverRadius: 4,
    fill: false,
  };
}

function consoleChartOptions(unitLabel) {
  return {
    responsive: true,
    maintainAspectRatio: true,
    plugins: {
      legend: {
        labels: {
          color: "#334155",
          boxWidth: 12,
          boxHeight: 12,
        },
      },
      tooltip: {
        callbacks: {
          label: (context) => `${context.dataset.label}: ${context.parsed.y} ${unitLabel}`,
        },
      },
    },
    scales: {
      x: {
        grid: { color: "rgba(100, 116, 139, 0.16)" },
        ticks: { color: "#64748b" },
      },
      y: {
        beginAtZero: true,
        grid: { color: "rgba(100, 116, 139, 0.16)" },
        ticks: { color: "#64748b" },
        title: { display: true, text: unitLabel, color: "#475569" },
      },
    },
  };
}
