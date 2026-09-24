import { SESSIONS_SHOWN, TIER_LABEL } from "./constants.js";
import { modelColor, quantiles, sumBy, totalOf } from "./data.js";
import { byId, clickable, el, swatch } from "./dom.js";
import { fmt, pct, secs, shortDay } from "./format.js";
import { dim, render, sessionLabel, state, toggle } from "./state.js";

const cell = (key, show) => ({ key, show });
const num = (value, show = fmt) => value ? cell(value, show(value)) : cell(null, "-");
const count = n => cell(n || 0, fmt(n || 0));
const sortKey = c => c?.show !== undefined ? c.key : c instanceof Node ? c.textContent : c;

function sortLines(tableId, lines) {
  const sort = state.sortState[tableId];
  if (!sort) return lines;
  return [...lines].sort((a, b) => {
    const x = sortKey(a.cells[sort.col]), y = sortKey(b.cells[sort.col]);
    if (x == null || y == null) return (x == null) - (y == null);
    return (typeof x === "number" ? x - y : String(x).localeCompare(String(y))) * sort.dir;
  });
}

function renderTable(table, headers, leftColumns, lines) {
  const head = el("tr"), sort = state.sortState[table.id];
  headers.forEach((h, i) => {
    const th = el("th", { scope: "col", ...(i < leftColumns ? { class: "l" } : {}) });
    if (sort?.col === i) th.setAttribute("aria-sort", sort.dir > 0 ? "ascending" : "descending");
    const button = el("button", { type: "button", title: "Sort by " + h }, h + (sort?.col === i ? (sort.dir > 0 ? " ↑" : " ↓") : ""));
    button.addEventListener("click", () => {
      state.sortState[table.id] = { col: i, dir: sort?.col === i ? -sort.dir : i < leftColumns ? 1 : -1 };
      render();
      table.querySelectorAll("th button")[i].focus();
    });
    th.append(button);
    head.append(th);
  });
  table.replaceChildren(head, ...lines.map(({ cells, onPick, active }) => {
    const tr = el("tr", active ? { class: "active" } : {});
    cells.forEach((c, i) => {
      const td = el("td", i < leftColumns ? { class: "l" } : {});
      td.append(c?.show !== undefined ? c.show : c);
      tr.append(td);
    });
    if (onPick) { tr.setAttribute("tabindex", "0"); clickable(tr, onPick); }
    return tr;
  }));
}

function named(color, text) { const span = el("span", { class: "clip", title: text }); span.append(swatch(color), text); return span; }
function clipped(text) { return el("span", { class: "clip narrow", title: text }, text); }

export function renderModelTable(byModel, total) {
  const ranked = [...byModel].sort((a, b) => b[1].aic - a[1].aic);
  const millions = digits => v => (v / 1e6).toFixed(digits);
  renderTable(byId("table"),
    ["Model", "Tier", "AIC", "Share", "Calls", "AIC / call", "Prompts", "Premium requests", "Input (M)", "Cached",
      "Cache write (M)", "Output (M)", "Reasoning (M)", "AIC / M output"], 2,
    sortLines("table", ranked.map(([model, v]) => ({
      active: state.picked.model === model, onPick: () => toggle("model", model),
      cells: [named(modelColor(model), model), TIER_LABEL[v.tier], cell(v.aic, fmt(v.aic)), total > 0 ? cell(v.aic / total, pct(v.aic / total)) : cell(null, "-"),
        cell(v.calls, fmt(v.calls)), v.calls ? cell(v.aic / v.calls, (v.aic / v.calls).toFixed(1)) : cell(null, "-"), num(v.prompts), num(v.premium),
        cell(v.in, millions(1)(v.in)), v.in ? cell(v.cache / v.in, pct(v.cache / v.in)) : cell(null, "-"), cell(v.cache_write, millions(1)(v.cache_write)),
        cell(v.out, millions(2)(v.out)), cell(v.reasoning, millions(2)(v.reasoning)), v.out ? num(v.aic / (v.out / 1e6)) : cell(null, "-")],
    }))));
}

export function renderSpeedTable(rows, byModel) {
  const time = ms => cell(ms, secs(ms));
  const lines = [...byModel].sort((a, b) => b[1].aic - a[1].aic).map(([model, v]) => {
    const own = rows.filter(r => r.model === model);
    const dur = quantiles(own, "dur"), ttft = quantiles(own, "ttft"), ottft = quantiles(own, "ottft");
    if (!dur.n) return null;
    return { cells: [named(modelColor(model), model), cell(dur.n, fmt(dur.n)), time(v.ms / dur.n), time(dur.p50), time(dur.p95),
      time(ttft.p50), time(ttft.p95), time(ottft.p50), v.itl_n ? num(v.itl / v.itl_n) : cell(null, "-"),
      v.ms ? num(v.out_timed / (v.ms / 1000)) : cell(null, "-")] };
  }).filter(Boolean);
  renderTable(byId("speed"), ["Model", "Timed calls", "Avg s", "p50 s", "p95 s", "First token p50 s", "First token p95 s",
    "First output p50 s", "Between tokens ms", "Output tokens / s"], 1, sortLines("speed", lines));
  const filtered = totalOf(rows, "filtered");
  byId("speed-sub").textContent = "Whole-call duration, time to first token (and to first visible output, after reasoning) and streaming pace per model. "
    + `Output tokens per second is end to end, so it includes the wait. ${fmt(filtered)} calls tripped the content filter.`;
}

function spanOf(session) {
  if (!session.start || !session.end) return "-";
  const minutes = (session.end - session.start) / 60;
  return minutes < 90 ? fmt(minutes) + " min" : minutes < 2880 ? (minutes / 60).toFixed(1) + " h" : fmt(minutes / 1440) + " d";
}

export function renderSessionTable(rows) {
  const { data } = state;
  const bySession = sumBy(rows, r => r.session);
  const subAic = sumBy(rows.filter(r => r.initiator === "sub-agent"), r => r.session);
  const lastDay = new Map(), topModel = new Map();
  for (const r of rows) {
    if (r.day > (lastDay.get(r.session) || "")) lastDay.set(r.session, r.day);
    const models = topModel.get(r.session) || topModel.set(r.session, new Map()).get(r.session);
    models.set(r.model, (models.get(r.model) || 0) + r.aic);
  }
  const ranked = [...bySession].sort((a, b) => b[1].aic - a[1].aic);
  const hasToolRuns = ranked.some(([id]) => data.sessions[id]?.tool_runs);
  const headers = ["Session", "Repository", "Branch", "Main model", "AIC", "Prompts", "Calls", "AIC / prompt", "Subagent spend",
    "Subagents", "Turns", "Files touched", "Compactions", "PRs / commits", "Open for", "Last spend"];
  if (hasToolRuns) headers.push("Failed commands");

  const lines = sortLines("session-table", ranked.map(([id, v]) => {
    const session = data.sessions[id] || {};
    const models = [...topModel.get(id)].sort((a, b) => b[1] - a[1]);
    const model = models[0][0] + (models.length > 1 ? ` +${models.length - 1}` : "");
    const cells = [named(modelColor(models[0][0]), sessionLabel(id)),
      dim("repo").show(session.repo || "-"), clipped(session.branch || "-"), model, cell(v.aic, fmt(v.aic)), num(v.prompts), cell(v.calls, fmt(v.calls)),
      v.prompts ? cell(v.aic / v.prompts, (v.aic / v.prompts).toFixed(1)) : cell(null, "-"),
      v.aic > 0 ? cell((subAic.get(id)?.aic || 0) / v.aic, pct((subAic.get(id)?.aic || 0) / v.aic)) : cell(null, "-"),
      count(session.subagents), count(session.turns), count(session.files), count(session.checkpoints),
      cell((session.prs || 0) + (session.commits || 0), `${session.prs || 0} / ${session.commits || 0}`),
      cell(session.start && session.end ? session.end - session.start : null, spanOf(session)),
      cell(lastDay.get(id), shortDay(lastDay.get(id)))];
    if (hasToolRuns) cells.push(session.tool_runs ? cell(session.tool_fails || 0, `${session.tool_fails || 0} of ${session.tool_runs}`) : cell(null, "-"));
    return { cells, active: state.picked.session === id, onPick: () => toggle("session", id) };
  }));
  renderTable(byId("session-table"), headers, 4, state.showAllSessions ? lines : lines.slice(0, SESSIONS_SHOWN));

  const more = byId("session-more");
  more.hidden = ranked.length <= SESSIONS_SHOWN;
  more.textContent = state.showAllSessions ? `Show top ${SESSIONS_SHOWN}` : `Show all ${ranked.length} sessions`;
}
