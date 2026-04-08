/**
 * AI QA Quality Dashboard — frontend logic
 *
 * Vanilla JS only.  No frameworks, no build step.
 * Uses fetch() against the FastAPI backend and Plotly.js for charts.
 *
 * Architecture:
 *  - api.*      pure async functions that call the backend and return JSON
 *  - render.*   pure functions that write DOM from data
 *  - init()     top-level coordinator; called once on DOMContentLoaded
 *  - refresh()  re-runs all fetches and renders (bound to the Refresh button)
 */

"use strict";

// ── API layer ──────────────────────────────────────────────────────────────

const api = {
  /**
   * @param {string} path
   * @returns {Promise<any>}
   */
  async get(path) {
    const resp = await fetch(path);
    if (!resp.ok) {
      const body = await resp.text().catch(() => "");
      throw new Error(`${resp.status} ${resp.statusText}: ${body}`);
    }
    return resp.json();
  },

  async summary() {
    return this.get("/api/metrics/summary");
  },

  async generatedTests(limit = 50, offset = 0) {
    return this.get(`/api/generated-tests?limit=${limit}&offset=${offset}`);
  },

  async flakyTests(limit = 50, offset = 0) {
    return this.get(`/api/flaky-tests?limit=${limit}&offset=${offset}`);
  },

  async flakyTrend(days = 30) {
    return this.get(`/api/flaky-tests/trend?days=${days}`);
  },

  async healedSelectors(limit = 50, offset = 0) {
    return this.get(`/api/healed-selectors?limit=${limit}&offset=${offset}`);
  },
};

// ── Utilities ──────────────────────────────────────────────────────────────

function fmtDate(isoStr) {
  if (!isoStr) return "—";
  const d = new Date(isoStr);
  return d.toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function fmtPct(val) {
  return typeof val === "number" ? val.toFixed(1) + "%" : "—";
}

function escapeHtml(str) {
  if (str == null) return "—";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function pill(text, variant) {
  return `<span class="pill pill--${variant}">${escapeHtml(text)}</span>`;
}

function setBadgeCount(sectionId, count) {
  const badge = document.querySelector(`[data-section="${sectionId}"] .badge`);
  if (badge) badge.textContent = count;
}

function showError(containerId, message) {
  const el = document.getElementById(containerId);
  if (el) el.innerHTML = `<div class="error-banner">${escapeHtml(message)}</div>`;
}

// ── Render: summary cards ──────────────────────────────────────────────────

function renderSummary(data) {
  const fields = {
    "stat-generated": { value: data.generated_tests_count, variant: "blue" },
    "stat-flaky-runs": { value: data.flaky_runs_count, variant: "yellow" },
    "stat-flaky-rate": { value: fmtPct(data.avg_flaky_rate), variant: "yellow" },
    "stat-healed": { value: data.healed_selectors_count, variant: "purple" },
  };

  for (const [id, cfg] of Object.entries(fields)) {
    const el = document.getElementById(id);
    if (el) {
      el.textContent = cfg.value;
      el.className = `card-value card-value--${cfg.variant}`;
    }
  }

  const lastEl = document.getElementById("stat-last-activity");
  if (lastEl) lastEl.textContent = fmtDate(data.last_activity_at);
}

// ── Render: flaky trend chart ──────────────────────────────────────────────

function renderTrendChart(trendData) {
  const container = document.getElementById("trend-chart");
  if (!container) return;

  if (!trendData || trendData.length === 0) {
    container.innerHTML = `<div class="empty-state"><span class="icon">📊</span>No trend data yet</div>`;
    return;
  }

  const dates = trendData.map((d) => d.date);
  const rates = trendData.map((d) => d.avg_flaky_rate);
  const counts = trendData.map((d) => d.run_count);

  const trace = {
    x: dates,
    y: rates,
    type: "scatter",
    mode: "lines+markers",
    name: "Avg Flaky Rate %",
    line: { color: "#f85149", width: 2.5, shape: "spline" },
    marker: { color: "#f85149", size: 6 },
    hovertemplate: "%{x}<br>Flaky rate: %{y:.1f}%<br>Runs: " +
      counts.map(String).join(",") + // injected as array lookup below
      "<extra></extra>",
    // Override hovertemplate per-point using customdata
    customdata: counts,
    hovertemplate: "%{x}<br>Flaky rate: %{y:.1f}%<br>Runs: %{customdata}<extra></extra>",
    fill: "tozeroy",
    fillcolor: "rgba(248,81,73,0.08)",
  };

  const layout = {
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: { family: "Inter, system-ui, sans-serif", size: 12, color: "#8b949e" },
    margin: { t: 10, r: 20, b: 40, l: 50 },
    xaxis: {
      gridcolor: "#21262d",
      linecolor: "#30363d",
      tickformat: "%b %d",
    },
    yaxis: {
      gridcolor: "#21262d",
      linecolor: "#30363d",
      ticksuffix: "%",
      rangemode: "tozero",
    },
    hovermode: "x unified",
    showlegend: false,
  };

  const config = {
    displayModeBar: false,
    responsive: true,
  };

  Plotly.newPlot(container, [trace], layout, config);
}

// ── Render: generated tests table ─────────────────────────────────────────

function renderGeneratedTests(rows) {
  const tbody = document.querySelector("#generated-tests-table tbody");
  if (!tbody) return;

  setBadgeCount("generated", rows.length);

  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">No generated tests yet</td></tr>`;
    return;
  }

  tbody.innerHTML = rows.map((r) => `
    <tr>
      <td>${fmtDate(r.created_at)}</td>
      <td>${pill(r.framework, "info")}</td>
      <td style="max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
          title="${escapeHtml(r.requirement_text)}">${escapeHtml(r.requirement_text)}</td>
      <td>${r.validation_passed ? pill("PASS", "pass") : pill("FAIL", "fail")}</td>
      <td style="font-variant-numeric:tabular-nums">${r.tokens_used.toLocaleString()}</td>
    </tr>
  `).join("");
}

// ── Render: flaky tests table ──────────────────────────────────────────────

function renderFlakyTests(runs) {
  const tbody = document.querySelector("#flaky-tests-table tbody");
  if (!tbody) return;

  setBadgeCount("flaky", runs.length);

  if (!runs.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">No flaky test runs yet</td></tr>`;
    return;
  }

  const rows = [];
  for (const run of runs) {
    const rateBadge =
      run.flaky_rate_pct > 50 ? pill(fmtPct(run.flaky_rate_pct), "fail") :
      run.flaky_rate_pct > 20 ? pill(fmtPct(run.flaky_rate_pct), "warn") :
      pill(fmtPct(run.flaky_rate_pct), "pass");

    rows.push(`
      <tr>
        <td>${fmtDate(run.analyzed_at)}</td>
        <td class="mono" style="font-size:.75rem">${escapeHtml(run.source_file || "—")}</td>
        <td style="font-variant-numeric:tabular-nums">${run.total_tests}</td>
        <td>${rateBadge}</td>
        <td>${run.flaky_count}</td>
      </tr>
    `);

    for (const result of run.results || []) {
      const suggestion = result.ai_suggestion
        ? `<details style="margin-top:.3rem">
             <summary style="cursor:pointer;font-size:.75rem;color:var(--accent-blue)">View AI suggestion</summary>
             <pre style="font-size:.72rem;white-space:pre-wrap;margin-top:.4rem;color:var(--text-secondary)">${escapeHtml(result.ai_suggestion)}</pre>
           </details>`
        : "";
      rows.push(`
        <tr style="background:var(--bg-elevated)">
          <td colspan="2" style="padding-left:2rem;color:var(--text-secondary);font-size:.8rem">
            ${escapeHtml(result.test_name)}${suggestion}
          </td>
          <td style="font-size:.8rem">${result.total_runs}</td>
          <td style="font-size:.8rem">${pill(fmtPct(result.fail_rate), result.fail_rate > 50 ? "fail" : "warn")}</td>
          <td style="font-size:.8rem;color:var(--text-secondary)">${result.avg_duration_seconds.toFixed(2)}s</td>
        </tr>
      `);
    }
  }

  tbody.innerHTML = rows.join("");
}

// ── Render: healed selectors table ────────────────────────────────────────

function renderHealedSelectors(rows) {
  const tbody = document.querySelector("#healed-selectors-table tbody");
  if (!tbody) return;

  setBadgeCount("healed", rows.length);

  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">No healed selectors yet</td></tr>`;
    return;
  }

  tbody.innerHTML = rows.map((r) => `
    <tr>
      <td>${fmtDate(r.healed_at)}</td>
      <td>${escapeHtml(r.description)}</td>
      <td class="mono" title="${escapeHtml(r.old_selector)}">${escapeHtml(r.old_selector)}</td>
      <td class="mono" style="color:var(--accent-green)" title="${escapeHtml(r.new_selector)}">${escapeHtml(r.new_selector)}</td>
      <td>${r.validation_passed ? pill("PASS", "pass") : pill("FAIL", "fail")}</td>
      <td style="font-variant-numeric:tabular-nums;text-align:center">${r.applied_count}</td>
    </tr>
  `).join("");
}

// ── Main ───────────────────────────────────────────────────────────────────

async function refresh() {
  const refreshBtn = document.getElementById("refresh-btn");
  if (refreshBtn) {
    refreshBtn.disabled = true;
    refreshBtn.textContent = "Refreshing…";
  }

  const tasks = [
    api.summary().then(renderSummary).catch((e) => showError("summary-error", e.message)),
    api.flakyTrend(30).then(renderTrendChart).catch((e) => console.error("trend:", e)),
    api.generatedTests().then(renderGeneratedTests).catch((e) => showError("generated-error", e.message)),
    api.flakyTests().then(renderFlakyTests).catch((e) => showError("flaky-error", e.message)),
    api.healedSelectors().then(renderHealedSelectors).catch((e) => showError("healed-error", e.message)),
  ];

  await Promise.allSettled(tasks);

  const lastRefreshEl = document.getElementById("last-refresh");
  if (lastRefreshEl) lastRefreshEl.textContent = new Date().toLocaleTimeString();

  if (refreshBtn) {
    refreshBtn.disabled = false;
    refreshBtn.textContent = "Refresh";
  }
}

async function init() {
  await refresh();

  // Auto-refresh every 60 seconds
  setInterval(refresh, 60_000);

  const refreshBtn = document.getElementById("refresh-btn");
  if (refreshBtn) refreshBtn.addEventListener("click", refresh);
}

document.addEventListener("DOMContentLoaded", init);
