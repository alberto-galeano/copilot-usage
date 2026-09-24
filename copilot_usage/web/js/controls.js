import { MEASURE_OPTIONS, RANGES } from "./constants.js";
import { byId, el } from "./dom.js";
import { clip } from "./format.js";
import { DIMS, pick, render, state, update } from "./state.js";

function exportCsv(rows) {
  const fields = Object.keys(rows[0] || {}).filter(f => !Array.isArray(rows[0][f]) && f !== "weekday");
  const quote = v => /[",\n]/.test(String(v)) ? `"${String(v).replaceAll('"', '""')}"` : v;
  const text = [fields.join(","), ...rows.map(r => fields.map(f => quote(r[f])).join(","))].join("\n");
  const link = el("a", { href: URL.createObjectURL(new Blob([text], { type: "text/csv" })), download: "copilot-usage.csv" });
  link.click();
  URL.revokeObjectURL(link.href);
}

function clearButton() {
  const clear = el("button", { type: "button", class: "clear" }, "Clear filters");
  clear.addEventListener("click", () => update({ picked: {} }));
  return clear;
}

function dateInputs() {
  const dates = el("span", { class: "dates" });
  dates.append(...["from", "to"].map(edge => {
    const input = el("input", { type: "date", value: state.range === "custom" ? state.custom[edge] : "" });
    if (state.range === "custom") input.classList.add("on");
    input.addEventListener("change", () => update({ custom: { ...state.custom, [edge]: input.value }, range: "custom" }));
    const label = el("label", { class: "inline" }, edge === "from" ? "From" : "to");
    label.append(input);
    return label;
  }));
  return dates;
}

function renderMeasureToggle() {
  byId("measure").replaceChildren(el("span", { class: "seg-label" }, "Show"), ...MEASURE_OPTIONS.map(([id, label]) => {
    const b = el("button", { type: "button", "aria-pressed": String(id === state.measure) }, label);
    b.addEventListener("click", () => update({ measure: id }));
    return b;
  }));
}

export function renderFilters(rows) {
  const { picked, filtersOpen } = state;
  const active = Object.keys(picked).length;
  const toggleFilters = el("button", { type: "button", "aria-expanded": String(filtersOpen), "aria-controls": "dims" },
    active ? `Filters · ${active}` : "Filters");
  toggleFilters.addEventListener("click", () => {
    state.filtersOpen = !state.filtersOpen;
    try { localStorage.setItem("filtersOpen", state.filtersOpen ? "1" : "0"); } catch {}
    render();
    byId("filters").querySelector("[aria-controls]").focus();
  });
  const csv = el("button", { type: "button", class: "clear" }, "Export CSV");
  csv.addEventListener("click", () => exportCsv(rows));
  const actions = el("span", { class: "push" });
  actions.append(toggleFilters, csv);

  byId("filters").replaceChildren(...RANGES.map(r => {
    const b = el("button", { type: "button", "aria-pressed": String(r.id === state.range) }, r.label);
    b.addEventListener("click", () => update({ range: r.id }));
    return b;
  }), el("span", { class: "gap" }), dateInputs(), actions);
  renderMeasureToggle();

  const dims = byId("dims");
  dims.hidden = !filtersOpen;
  dims.replaceChildren(...DIMS.filter(d => !d.chipOnly).map(d => {
    const values = [...new Set(state.data.rows.map(r => r[d.id]))].sort();
    const select = el("select");
    select.append(el("option", { value: "" }, "All"));
    for (const v of values) select.append(el("option", { value: v }, d.show(v)));
    select.value = values.includes(picked[d.id]) ? picked[d.id] : "";
    if (select.value) select.classList.add("on");
    select.addEventListener("change", () => pick(d.id, select.value));
    const label = el("label", {}, d.label);
    label.append(select);
    return label;
  }));

  const chips = byId("chips");
  chips.replaceChildren(...DIMS.filter(d => picked[d.id]).map(d => {
    const text = `${d.label}: ${clip(d.show(picked[d.id]), 300)}`;
    const chip = el("button", { type: "button", class: "chip", "aria-label": "Remove filter " + text }, text + " ×");
    chip.addEventListener("click", () => pick(d.id, ""));
    return chip;
  }));
  if (active > 1) chips.append(clearButton());
}

export function renderNotice(rows) {
  const notice = byId("notice");
  notice.hidden = rows.length > 0;
  if (rows.length) return;
  const widen = el("button", { type: "button" }, "Show all time");
  widen.addEventListener("click", () => update({ range: "all" }));
  notice.replaceChildren("No usage matches this date range and filters.",
    ...(Object.keys(state.picked).length ? [clearButton()] : []), ...(state.range !== "all" ? [widen] : []));
}
