import { modelColor } from "./data.js";
import { byId, clickable, el, swatch } from "./dom.js";
import { fmt } from "./format.js";
import { dim, state, toggle } from "./state.js";

function ago(epoch) {
  const sec = Math.max(0, Date.now() / 1000 - epoch);
  if (sec < 60) return "just now";
  if (sec < 3600) return Math.floor(sec / 60) + " min ago";
  if (sec < 86400) return Math.floor(sec / 3600) + " h ago";
  return Math.floor(sec / 86400) + " d ago";
}

export function renderOpenSessions() {
  const host = byId("sessions");
  const { active } = state.server;
  if (!active.length) return host.replaceChildren(el("div", { class: "empty" }, "No sessions running"));
  host.replaceChildren(...active.map(a => {
    const row = el("div", { class: "session", tabindex: "0" });
    const title = el("div", { class: "title" });
    title.append(swatch(modelColor(a.model, a.tier)), a.name);
    const burn = a.burn > 0.5 ? ` · burning ${fmt(a.burn)} AIC/h` : "";
    const where = a.branch && a.branch !== "-" ? `${dim("repo").show(a.repo)} @ ${a.branch}` : a.repo;
    row.append(title, el("div", { class: "aic" }, fmt(a.aic) + " AIC"),
      el("div", { class: "meta" }, `${a.model} · ${where} · active ${ago(a.last)}${burn}`));
    clickable(row, () => toggle("session", a.id));
    return row;
  }));
}
