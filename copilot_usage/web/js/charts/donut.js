import { MEASURE_TEXT, MIX_SLICES, TIERS } from "../constants.js";
import { modelColor } from "../data.js";
import { byId, clickable, el, roving, s, swatch } from "../dom.js";
import { css, fmt, pct } from "../format.js";
import { toggle } from "../state.js";
import { hoverable } from "../tooltip.js";

function mixSlices(byModel, field) {
  const ranked = [...byModel].map(([model, v]) => ({ model, tier: v.tier, value: Math.max(0, v[field]) }))
    .filter(e => e.value > 0).sort((a, b) => b.value - a.value);
  const kept = ranked.length > MIX_SLICES ? ranked.slice(0, MIX_SLICES - 1) : ranked;
  const rest = ranked.slice(kept.length);
  if (rest.length) kept.push({ model: `${rest.length} others`, value: rest.reduce((a, e) => a + e.value, 0) });
  return kept;
}

const tierRank = slice => slice.tier ? TIERS.indexOf(slice.tier) : TIERS.length;
const colorOf = slice => slice.tier ? modelColor(slice.model) : css("neutral");
const pickModel = slice => () => toggle("model", slice.model);

export function renderDonut(hostId, byModel, field) {
  const host = byId(hostId), { unit, noun } = MEASURE_TEXT[field];
  const slices = mixSlices(byModel, field), total = slices.reduce((a, e) => a + e.value, 0);
  if (!total) return host.replaceChildren(el("div", { class: "empty" }, "No " + noun));
  const size = 150, c = size / 2, r = 58, around = 2 * Math.PI * r, gap = slices.length > 1 ? 2 : 0;
  const svg = s("svg", { viewBox: `0 0 ${size} ${size}`, height: size, role: "group", "aria-label": `Share of ${noun} by model` });
  const legend = el("div", { class: "mix-legend" });
  let start = 0;
  for (const slice of [...slices].sort((a, b) => tierRank(a) - tierRank(b))) {
    const color = colorOf(slice), length = slice.value / total * around;
    const arc = s("circle", { class: "slice mark", cx: c, cy: c, r, fill: "none", stroke: "currentColor",
      style: `color:${color}`, "stroke-dasharray": `${Math.max(0, length - gap)} ${around}`, "stroke-dashoffset": -start,
      transform: `rotate(-90 ${c} ${c})` });
    hoverable(arc, slice.model, [{ color, value: `${fmt(slice.value)} ${unit}`, label: `${pct(slice.value / total)} of ${noun}` }]);
    if (slice.tier) clickable(arc, pickModel(slice));
    svg.append(arc);
    start += length;
  }
  for (const slice of slices) {
    const row = el("div", { class: "mix-row" });
    const name = el("span", { class: "name", title: slice.model });
    name.append(swatch(colorOf(slice)), slice.model);
    row.append(name, el("b", {}, fmt(slice.value)), el("span", {}, pct(slice.value / total)));
    if (slice.tier) {
      clickable(row, pickModel(slice));
      row.setAttribute("tabindex", "0");
    }
    legend.append(row);
  }
  svg.append(s("text", { class: "total", x: c, y: c + 4, "text-anchor": "middle" }, fmt(total)),
    s("text", { x: c, y: c + 22, "text-anchor": "middle" }, unit));
  roving(svg);
  host.replaceChildren(svg, legend);
}
