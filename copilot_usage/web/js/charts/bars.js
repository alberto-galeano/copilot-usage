import { MEASURE_TEXT, TOKEN_KINDS } from "../constants.js";
import { sumBy, totalOf } from "../data.js";
import { byId, clickable, el, roving, s } from "../dom.js";
import { clip, css, fmt, pct } from "../format.js";
import { state, toggle } from "../state.js";
import { hoverable } from "../tooltip.js";

function roundedRight(x, y, w, h, r) {
  r = Math.min(r, w, h / 2);
  return `M${x},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h - r}Q${x + w},${y + h} ${x + w - r},${y + h}H${x}Z`;
}

export function renderBars(hostId, label, entries, total, limit = 6) {
  const { measure } = state;
  const host = byId(hostId), { unit, noun } = MEASURE_TEXT[measure];
  const ranked = entries.filter(e => e[measure] > 0.5).sort((a, b) => b[measure] - a[measure]);
  if (!ranked.length) return host.replaceChildren(el("div", { class: "empty" }, "No " + noun));
  const shown = ranked.slice(0, limit);
  const W = host.clientWidth || 300, rowH = 36, H = shown.length * rowH, valueRoom = 92;
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "group", "aria-label": `${noun} by ${label}` });
  shown.forEach((entry, i) => {
    const value = entry[measure];
    const y0 = i * rowH, w = Math.max(2, (value / shown[0][measure]) * (W - valueRoom));
    const name = s("text", { class: "name", x: 0, y: y0 + 12 }, clip(entry.name, W));
    if (entry.active) name.style.fontWeight = 600;
    svg.append(name);
    svg.append(s("path", { class: entry.color ? "mark" : "", d: roundedRight(0, y0 + 17, w, 10, 4), fill: "currentColor", style: `color:${entry.color || css("neutral")}` }));
    svg.append(s("text", { class: "val", x: w + 6, y: y0 + 26 }, `${fmt(value)} · ${pct(value / total)}`));
    const hit = s("rect", { class: "hit", x: 0, y: y0, width: W, height: rowH - 2, rx: 4 });
    const lines = [{ color: entry.color || css("neutral"), value: `${fmt(value)} ${unit}`, label: `${pct(value / total)} of ${noun}` }];
    const other = measure === "calls" ? "aic" : "calls";
    if (entry[other] != null) lines.push({ value: fmt(entry[other]), label: MEASURE_TEXT[other].unit });
    hoverable(hit, entry.title || entry.name, lines);
    if (entry.onPick) clickable(hit, entry.onPick);
    svg.append(hit);
  });
  roving(svg);
  host.replaceChildren(svg);
  if (ranked.length > shown.length) host.append(el("p", { class: "sub" }, `and ${ranked.length - shown.length} more under Filters`));
}

export function dimEntries(d, rows, colorOf) {
  return [...sumBy(rows, r => r[d.id])].map(([value, v]) => ({
    name: d.show(value), title: value, aic: v.aic, calls: v.calls, color: colorOf?.(value),
    active: state.picked[d.id] === value, onPick: () => toggle(d.id, value),
  }));
}

export function renderTokenKinds(rows, total) {
  const entries = TOKEN_KINDS.map(([field, name]) => ({ name, aic: totalOf(rows, field) }));
  const itemized = entries.reduce((a, e) => a + e.aic, 0);
  entries.push({ name: "Not itemized (session logs)", aic: total - itemized });
  renderBars("by-tokens", "token type", entries, total);
}
