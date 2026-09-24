import { MEASURE_TEXT, WEEKDAYS } from "../constants.js";
import { sumBy } from "../data.js";
import { byId, el, roving, s, swatch } from "../dom.js";
import { css, fmt } from "../format.js";
import { state } from "../state.js";
import { hoverable } from "../tooltip.js";

export function renderHeatmap(rows) {
  const { measure } = state;
  const host = byId("heatmap");
  const cells = sumBy(rows, r => r.weekday * 24 + r.hour);
  const { unit } = MEASURE_TEXT[measure], other = measure === "calls" ? "aic" : "calls";
  const max = Math.max(0, ...[...cells.values()].map(v => v[measure]));
  const W = host.clientWidth || 600, left = 36, topRoom = 16, gap = 2;
  const size = (W - left) / 24, H = topRoom + size * 7;
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "group", "aria-label": "Spend by weekday and hour" });
  for (let h = 0; h < 24; h += 3) svg.append(s("text", { x: left + size * h + size / 2, y: 10, "text-anchor": "middle" }, String(h).padStart(2, "0")));
  WEEKDAYS.forEach((name, d) => {
    svg.append(s("text", { x: 0, y: topRoom + size * d + size / 2 + 4 }, name));
    for (let h = 0; h < 24; h++) {
      const v = cells.get(d * 24 + h), value = Math.max(0, v?.[measure] || 0);
      const cell = s("rect", { x: left + size * h + gap / 2, y: topRoom + size * d + gap / 2, width: size - gap, height: size - gap, rx: 3,
        class: value > 0.5 ? "mark" : "", style: `color:${css("high")}`,
        fill: value > 0.5 ? "currentColor" : css("grid"), "fill-opacity": value > 0.5 ? 0.12 + 0.88 * (value / max) : 0.6 });
      hoverable(cell, `${name} ${String(h).padStart(2, "0")}:00`, [
        { color: css("high"), value: `${fmt(value)} ${unit}`, label: v ? `${fmt(v[other])} ${MEASURE_TEXT[other].unit}` : "no calls" }]);
      svg.append(cell);
    }
  });
  roving(svg, 24);
  host.replaceChildren(svg);
  const scale = el("div", { class: "legend scale" });
  scale.append("0", ...[0.12, 0.4, 0.7, 1].map(o => { const sw = swatch(css("high")); sw.style.opacity = o; return sw; }), `${fmt(max)} ${unit} per hour slot`);
  host.append(scale);
}
