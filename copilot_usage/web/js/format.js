export const fmt = n => Math.round(n).toLocaleString("en-US");
export const usd = aic => "$" + (aic / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const pct = x => Math.round(x * 100) + "%";
export const secs = ms => ms == null ? "-" : (ms / 1000).toFixed(1);
export const css = name => `var(--${name})`;

export function addDays(date, n) { const d = new Date(date); d.setDate(d.getDate() + n); return d; }
export function iso(date) { return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`; }
export function parseDay(day) { const [y, m, d] = day.split("-").map(Number); return new Date(y, m - 1, d); }
export function shortDay(day) { return parseDay(day).toLocaleDateString("en-US", { month: "short", day: "numeric" }); }
export function clip(text, width) { const max = Math.max(8, Math.floor(width / 7.4)); return text.length > max ? text.slice(0, max - 1) + "…" : text; }
export function when(epoch) {
  const moment = new Date(epoch * 1000), time = moment.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return iso(moment) === iso(new Date()) ? time : `${shortDay(iso(moment))} ${time}`;
}
