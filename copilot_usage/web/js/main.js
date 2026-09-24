import { renderBars, dimEntries, renderTokenKinds } from "./charts/bars.js";
import { renderDonut } from "./charts/donut.js";
import { renderHeatmap } from "./charts/heatmap.js";
import { renderSpend } from "./charts/spend.js";
import { MEASURE_TEXT } from "./constants.js";
import { renderFilters, renderNotice } from "./controls.js";
import { ingest, modelColor, officialPlan, sliceRows, sumBy, totalOf } from "./data.js";
import { byId } from "./dom.js";
import { renderKpis } from "./kpis.js";
import { renderOpenSessions } from "./open-sessions.js";
import { dim, onRender, readState, render, state } from "./state.js";
import { renderModelTable, renderSessionTable, renderSpeedTable } from "./tables.js";
import { initSettings } from "./theme.js";
import { hideTip } from "./tooltip.js";

function renderHeadings() {
  const { noun, what } = MEASURE_TEXT[state.measure], byCalls = state.measure === "calls";
  byId("models-title").textContent = byCalls ? "Calls by model" : "Spend by model";
  byId("models-sub").textContent = `${what}, colored by tier. Click a model to filter by it.`;
  byId("breakdown-title").textContent = byCalls ? "Where the calls go" : "Where the spend goes";
  byId("breakdown-sub").textContent = `${what} by each dimension. Click a bar to filter by it.`
    + (byCalls ? "" : " Token type splits the bill by what was charged for.");
  byId("tokens-block").hidden = byCalls;
  byId("heatmap-title").textContent = byCalls ? "When the calls happen" : "When the spend happens";
  byId("heatmap-sub").textContent = `${what} by weekday and hour of day, local time.`;
}

function renderClients(rows, measured) {
  const entries = dimEntries(dim("client"), rows), plan = officialPlan();
  if (!plan || state.measure !== "aic" || plan.outside < 0.5) return renderBars("by-client", dim("client").label, entries, measured);
  entries.push({ name: "Outside this machine", title: "VS Code, github.com and other computers, per GitHub", aic: plan.outside });
  renderBars("by-client", dim("client").label, entries, measured + plan.outside);
}

function renderPage() {
  if (!state.data) return;
  hideTip();
  const { rows, days, previous } = sliceRows();
  renderFilters(rows);
  renderNotice(rows);
  const byTier = sumBy(rows, r => r.tier), byModel = sumBy(rows, r => r.model);
  const total = totalOf(rows, "aic");
  renderKpis(rows, previous, days, byTier);
  const measured = totalOf(rows, state.measure);
  renderHeadings();
  renderSpend(rows, days);
  renderBars("models", "model", dimEntries(dim("model"), rows, modelColor), measured, 8);
  renderDonut("mix-aic", byModel, "aic");
  renderDonut("mix-calls", byModel, "calls");
  for (const id of ["repo", "branch", "effort", "initiator", "endpoint", "finish", "host"])
    renderBars("by-" + id, dim(id).label, dimEntries(dim(id), rows), measured);
  renderClients(rows, measured);
  if (state.measure === "aic") renderTokenKinds(rows, total);
  renderHeatmap(rows);
  renderSessionTable(rows);
  renderModelTable(byModel, total);
  renderSpeedTable(rows, byModel);
  renderOpenSessions();
}

async function refresh() {
  const status = byId("status");
  try {
    const changed = ingest(await (await fetch("/api/usage?v=" + encodeURIComponent(state.version))).json());
    document.querySelector("main").classList.remove("loading");
    if (changed) render(); else renderOpenSessions();
    status.classList.remove("stale");
    byId("updated").textContent = "Live · updated " + new Date().toLocaleTimeString();
  } catch {
    status.classList.add("stale");
    byId("updated").textContent = "Server not reachable, showing the last data. Retrying";
  }
}

onRender(renderPage);
try { readState(location.hash.slice(1) || localStorage.getItem("state") || ""); } catch {}
addEventListener("hashchange", () => { readState(location.hash.slice(1)); render(); });
initSettings();

byId("session-more").addEventListener("click", () => { state.showAllSessions = !state.showAllSessions; render(); });
let lastWidth = innerWidth, resizeTimer;
addEventListener("resize", () => {
  // Mobile browsers fire resize when the URL bar collapses; only width changes the charts.
  if (innerWidth === lastWidth) return;
  lastWidth = innerWidth;
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(render, 120);
});
refresh();
setInterval(refresh, 5000);
