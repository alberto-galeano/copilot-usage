import { MEASURE_TEXT, PLOT, TIERS, TIER_LABEL } from "../constants.js";
import { niceMax, sumBy } from "../data.js";
import { byId, clickable, el, roving, s, swatch } from "../dom.js";
import { css, fmt, pct, shortDay } from "../format.js";
import { state, update } from "../state.js";
import { hoverable } from "../tooltip.js";

function roundedTop(x, y, w, h, r) {
  r = Math.min(r, h, w / 2);
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}

function timeSlots(days) {
  if (days.length === 1)
    return { hourly: true, slotOf: r => r.hour,
      slots: Array.from({ length: 24 }, (_, h) => ({ key: h, label: String(h).padStart(2, "0") + ":00" })) };
  return { hourly: false, slotOf: r => r.day, slots: days.map(d => ({ key: d, label: shortDay(d) })) };
}

export function renderSpend(rows, days) {
  const host = byId("daily");
  const { measure, server, range } = state;
  const { hourly, slotOf, slots } = timeSlots(days);
  const byCalls = measure === "calls", { unit, noun, what } = MEASURE_TEXT[measure];
  byId("daily-title").textContent = `${hourly ? "Hourly" : "Daily"} ${noun} by tier`;
  const price = byCalls ? "" : " 1 AIC = $0.01.";
  byId("daily-sub").textContent = hourly
    ? `${what} per hour on ${shortDay(days[0])}.${price}`
    : `${what} per day.${price} Click a day to see it by hour.`;

  const W = host.clientWidth || 600, H = 240, m = PLOT;
  const plotW = W - m.left - m.right, plotH = H - m.top - m.bottom;
  const bySlot = new Map(slots.map(slot => [slot.key, Object.fromEntries(TIERS.map(t => [t, 0]))]));
  for (const r of rows) if (bySlot.has(slotOf(r))) bySlot.get(slotOf(r))[r.tier] += r[measure];
  for (const v of bySlot.values()) for (const t of TIERS) v[t] = Math.max(0, v[t]);

  const now = new Date();
  const dailyBudget = server.budget && range === "month" && !hourly && !byCalls
    ? server.budget / new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate() : 0;
  const top = niceMax(Math.max(dailyBudget, ...[...bySlot.values()].map(v => TIERS.reduce((a, t) => a + v[t], 0))));
  const y = v => m.top + plotH - (v / top) * plotH;
  const slotW = plotW / slots.length;
  const barW = Math.max(2, Math.min(24, slotW - 2));
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "group", "aria-label": `${byCalls ? "Calls" : "Spend"} by tier over time` });

  for (let i = 0; i <= 4; i++) {
    const v = (top / 4) * i;
    svg.append(s("line", { x1: m.left, x2: W - m.right, y1: y(v), y2: y(v), stroke: i ? css("grid") : css("axis") }));
    svg.append(s("text", { x: m.left - 8, y: y(v) + 4, "text-anchor": "end" }, top < 8 ? v.toFixed(1) : fmt(v)));
  }

  const labelEvery = Math.ceil(slots.length / Math.max(1, Math.floor(plotW / 70)));
  slots.forEach((slot, i) => {
    const cx = m.left + slotW * i + slotW / 2, x = cx - barW / 2;
    const values = bySlot.get(slot.key);
    const present = TIERS.filter(t => values[t] > 0);
    let base = 0;
    present.forEach((tier, idx) => {
      const y1 = y(base + values[tier]), y0 = y(base) - (idx ? 2 : 0);
      const isTop = idx === present.length - 1;
      svg.append(s("path", { class: "mark", d: roundedTop(x, y1, barW, Math.max(1, y0 - y1), isTop ? 4 : 0), fill: "currentColor", style: `color:${css(tier)}` }));
      base += values[tier];
    });
    if (i % labelEvery === 0) svg.append(s("text", { x: cx, y: H - 6, "text-anchor": "middle" }, slot.label));

    const hit = s("rect", { class: "hit", x: m.left + slotW * i, y: m.top, width: slotW, height: plotH });
    hoverable(hit, `${slot.label} · ${fmt(base)} ${unit}`,
      TIERS.map(t => ({ color: css(t), value: fmt(values[t]), label: TIER_LABEL[t] })));
    if (!hourly) clickable(hit, () => update({ custom: { from: slot.key, to: slot.key }, range: "custom" }));
    svg.append(hit);
  });

  if (dailyBudget)
    svg.append(s("line", { x1: m.left, x2: W - m.right, y1: y(dailyBudget), y2: y(dailyBudget),
      stroke: css("text-2"), "stroke-dasharray": "4 4", "pointer-events": "none" }));
  roving(svg);
  host.replaceChildren(svg);
  renderLegend(dailyBudget);
  renderCacheRate(rows, slots, slotOf);
}

function renderLegend(dailyBudget) {
  const items = TIERS.map(t => {
    const item = el("span");
    item.append(swatch(css(t)), TIER_LABEL[t]);
    return item;
  });
  if (dailyBudget) {
    const item = el("span");
    item.append(el("span", { class: "dash" }), `Budget, ${fmt(dailyBudget)} AIC / day`);
    items.push(item);
  }
  byId("legend").replaceChildren(...items);
}

function renderCacheRate(rows, slots, slotOf) {
  const host = byId("cache-rate");
  const W = host.clientWidth || 600, H = 96, m = { ...PLOT, top: 10 };
  const plotW = W - m.left - m.right, plotH = H - m.top - m.bottom;
  const bySlot = sumBy(rows, slotOf);
  const slotW = plotW / slots.length;
  const y = share => m.top + plotH - share * plotH;
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "group", "aria-label": "Cache hit rate over time" });
  for (const share of [0, 0.5, 1]) {
    svg.append(s("line", { x1: m.left, x2: W - m.right, y1: y(share), y2: y(share), stroke: share ? css("grid") : css("axis") }));
    svg.append(s("text", { x: m.left - 8, y: y(share) + 4, "text-anchor": "end" }, pct(share)));
  }
  let path = "", pen = "M";
  slots.forEach((slot, i) => {
    const v = bySlot.get(slot.key);
    if (!v || !v.in) { pen = "M"; return; }
    const cx = m.left + slotW * i + slotW / 2, share = v.cache / v.in;
    path += `${pen}${cx},${y(share)}`; pen = "L";
    if (slots.length <= 45) svg.append(s("circle", { cx, cy: y(share), r: 3, fill: css("neutral"), stroke: css("surface"), "stroke-width": 2 }));
    const hit = s("rect", { class: "hit", x: m.left + slotW * i, y: m.top, width: slotW, height: plotH });
    hoverable(hit, slot.label, [
      { color: css("neutral"), value: pct(share), label: "of input read from cache" },
      { value: fmt(v.saved) + " AIC", label: "saved vs uncached input" },
    ]);
    svg.append(hit);
  });
  svg.prepend(s("path", { d: path, fill: "none", stroke: css("neutral"), "stroke-width": 2, "stroke-linejoin": "round" }));
  roving(svg);
  host.replaceChildren(svg);
}
