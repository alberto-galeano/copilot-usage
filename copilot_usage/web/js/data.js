import { MEASURES, RANGES } from "./constants.js";
import { addDays, css, iso, parseDay } from "./format.js";
import { DIMS, state } from "./state.js";

export function ingest(next) {
  state.server = next;
  if (!next.rows) return false;
  state.version = next.version;
  const rows = next.rows.map(values => {
    const r = Object.fromEntries(next.fields.map((f, i) => [f, values[i]]));
    const session = next.sessions[r.session] || {};
    r.repo = session.repo || "-"; r.branch = session.branch || "-"; r.host = session.host || "unknown";
    r.client = session.client || "Copilot CLI";
    r.tier = next.tiers[r.model];
    r.weekday = (parseDay(r.day).getDay() + 6) % 7;
    return r;
  });
  state.data = { rows, sessions: next.sessions, tiers: next.tiers };
  return true;
}

const matches = r => DIMS.every(d => !state.picked[d.id] || r[d.id] === state.picked[d.id]);

export function sliceRows() {
  const { data, range, custom } = state;
  const today = iso(new Date());
  const firstDay = data.rows.length ? data.rows[0].day : today;
  let start, end = today;
  if (range === "custom") {
    start = custom.from || firstDay;
    end = custom.to || today;
  } else {
    const startDate = RANGES.find(r => r.id === range).start(new Date());
    start = startDate ? iso(startDate) : firstDay;
  }
  const rows = data.rows.filter(r => r.day >= start && r.day <= end && matches(r));
  const days = [];
  for (let d = parseDay(start); iso(d) <= end && days.length < 800; d = addDays(d, 1)) days.push(iso(d));

  // Only compare against a previous window the data fully covers.
  const prevStart = iso(addDays(parseDay(start), -days.length)), prevEnd = iso(addDays(parseDay(start), -1));
  const previous = range !== "all" && days.length && firstDay <= prevStart
    ? data.rows.filter(r => r.day >= prevStart && r.day <= prevEnd && matches(r)) : null;
  return { rows, days, previous };
}

export function sumBy(rows, keyOf) {
  const out = new Map();
  for (const r of rows) {
    const key = keyOf(r);
    let acc = out.get(key);
    if (!acc) out.set(key, acc = { ...Object.fromEntries(MEASURES.map(f => [f, 0])), tier: r.tier });
    for (const f of MEASURES) acc[f] += r[f];
  }
  return out;
}
export const totalOf = (rows, field) => rows.reduce((a, r) => a + r[field], 0);

export function quantiles(rows, field) {
  const values = rows.flatMap(r => r[field]).sort((a, b) => a - b);
  const at = q => values.length ? values[Math.min(values.length - 1, Math.floor(q * values.length))] : null;
  return { n: values.length, p50: at(0.5), p95: at(0.95) };
}

export function niceMax(value) {
  if (value <= 0) return 1;
  const pow = 10 ** Math.floor(Math.log10(value));
  return [1, 2, 2.5, 5, 10].map(m => m * pow).find(v => v >= value);
}

// Models in the same tier share a hue and differ by strength, fixed by name so a model keeps its color under any filter.
export function modelColor(model, tier = state.data.tiers[model]) {
  if (!tier) return css("neutral");
  const tiers = state.data.tiers;
  const peers = Object.keys(tiers).filter(m => tiers[m] === tier).sort();
  const strength = 1 - 0.6 * Math.max(0, peers.indexOf(model)) / Math.max(1, peers.length - 1);
  return `color-mix(in srgb, ${css(tier)} ${Math.round(strength * 100)}%, transparent)`;
}
