import { MEASURE_OPTIONS, RANGES, TIER_LABEL } from "./constants.js";

export const state = {
  data: null, server: {}, version: "",
  range: "month", custom: { from: "", to: "" }, picked: {}, measure: "aic",
  filtersOpen: false, showAllSessions: false, sortState: {},
};
try { state.filtersOpen = localStorage.getItem("filtersOpen") === "1"; } catch {}

export const sessionLabel = id => state.data.sessions[id]?.label || id.slice(0, 8);

export const DIMS = [
  { id: "tier", label: "Tier", show: v => TIER_LABEL[v] || v },
  { id: "model", label: "Model", show: v => v },
  { id: "repo", label: "Repository", show: v => v.split("/").pop() },
  { id: "branch", label: "Branch", show: v => v },
  { id: "effort", label: "Reasoning effort", show: v => v },
  { id: "initiator", label: "Initiator", show: v => v },
  { id: "endpoint", label: "API endpoint", show: v => v },
  { id: "finish", label: "Finish reason", show: v => v },
  { id: "host", label: "Host", show: v => v },
  { id: "client", label: "Client", show: v => v },
  { id: "session", label: "Session", show: sessionLabel, chipOnly: true },
];
export const dim = id => DIMS.find(d => d.id === id);

// main.js registers the page renderer, so modules can re-render without importing it back.
let renderer = () => {};
export function onRender(fn) { renderer = fn; }
export function render() { renderer(); }

export function readState(text) {
  const params = new URLSearchParams(text);
  let range = params.get("range") || "month";
  if (range !== "custom" && !RANGES.some(r => r.id === range)) range = "month";
  state.range = range;
  state.custom = { from: params.get("from") || "", to: params.get("to") || "" };
  state.measure = MEASURE_OPTIONS.some(([id]) => id === params.get("by")) ? params.get("by") : "aic";
  state.picked = {};
  for (const d of DIMS) if (params.get(d.id)) state.picked[d.id] = params.get(d.id);
}

function remember() {
  const params = new URLSearchParams({ range: state.range });
  if (state.range === "custom") { params.set("from", state.custom.from); params.set("to", state.custom.to); }
  if (state.measure !== "aic") params.set("by", state.measure);
  for (const [id, value] of Object.entries(state.picked)) params.set(id, value);
  history.replaceState(null, "", "#" + params);
  try { localStorage.setItem("state", params.toString()); } catch {}
}

export function update(changes) {
  Object.assign(state, changes);
  remember();
  render();
}

export function pick(id, value) {
  const picked = { ...state.picked };
  if (value) picked[id] = value; else delete picked[id];
  update({ picked });
}
export function toggle(id, value) { pick(id, state.picked[id] === value ? "" : value); }
