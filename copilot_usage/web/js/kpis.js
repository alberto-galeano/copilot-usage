import { MEASURE_TEXT, TIERS, TIER_LABEL } from "./constants.js";
import { officialPlan, totalOf } from "./data.js";
import { byId, el } from "./dom.js";
import { css, fmt, pct, usd, when } from "./format.js";
import { state } from "./state.js";

export function renderKpis(rows, previous, days, byTier) {
  const { range, server, measure } = state;
  const total = totalOf(rows, "aic"), calls = totalOf(rows, "calls"), prompts = totalOf(rows, "prompts");
  const closedAic = rows.filter(r => r.calls > 0).reduce((a, r) => a + r.aic, 0);
  const tierAic = t => Math.max(0, byTier.get(t)?.aic || 0);
  const tierCalls = t => byTier.get(t)?.calls || 0;

  const plan = officialPlan(), shown = plan ? plan.used : total;
  const spend = byId("k-spend");
  spend.replaceChildren(fmt(shown), el("span", { class: "unit" }, "AIC"));
  spend.title = plan ? `Plan usage per GitHub as of ${when(plan.reported_at)}, plus this machine's calls since` : "";
  const note = [usd(shown) + " at list price"];
  const before = previous ? totalOf(previous, "aic") : 0;
  if (before > 0.5) {
    const change = total / before - 1;
    note.push(" · ", el("span", { class: "delta" }, `${change >= 0 ? "↑" : "↓"} ${pct(Math.abs(change))}`),
      ` vs the ${days.length === 1 ? "day" : days.length + " days"} before`);
  }
  byId("k-spend-note").replaceChildren(...note);
  let pace = "";
  const budget = byId("k-budget");
  budget.hidden = !(range === "month" && server.budget);
  if (range === "month") {
    const spent = server.plan ? server.plan.used : total;
    const limitName = server.plan && server.plan.limit === server.budget ? "plan" : "budget";
    const now = new Date(), monthDays = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
    const projected = spent / now.getDate() * monthDays;
    pace = `On pace for ${fmt(projected)} AIC (${usd(projected)}) this month`;
    if (server.budget) {
      pace = `On pace for ${fmt(projected)} AIC, ${pct(projected / server.budget)} of ${limitName}`;
      const used = spent / server.budget;
      const [status, statusLabel] = used >= 1 ? ["danger", `Over ${limitName}`]
        : projected > server.budget ? ["warn", "On pace to go over"] : ["ok", "On track"];
      budget.className = "budget " + status;
      const meter = byId("k-meter");
      meter.setAttribute("aria-label", `Monthly ${limitName} used`);
      meter.setAttribute("aria-valuemax", server.budget);
      meter.setAttribute("aria-valuenow", Math.round(spent));
      meter.querySelector(".fill").style.width = Math.min(1, used) * 100 + "%";
      meter.querySelector(".mark").style.left = now.getDate() / monthDays * 100 + "%";
      byId("k-budget-note").replaceChildren(el("b", { class: "state" }, statusLabel),
        ` · ${pct(used)} of ${fmt(server.budget)} AIC ${limitName}`);
    }
  }
  byId("k-spend-pace").textContent = pace;

  const measured = totalOf(rows, measure);
  const tierShare = t => Math.max(0, byTier.get(t)?.[measure] || 0) / measured;
  byId("k-share-label").textContent = `High tier share of ${MEASURE_TEXT[measure].noun}`;
  byId("k-share").textContent = measured > 0 ? pct(tierShare("high")) : "-";
  let shareNote = measure === "aic"
    ? calls ? `${pct(tierCalls("high") / calls)} of calls went to high tier models.` : ""
    : total > 0 ? `${pct(tierAic("high") / total)} of spend went to high tier models.` : "";
  const p = byTier.get("high"), mid = byTier.get("medium");
  if (p?.calls && mid?.calls) {
    const saving = p.aic - p.calls * (mid.aic / mid.calls);
    if (saving > 0.5) shareNote += ` At the medium tier rate per call they'd cost ${fmt(saving)} AIC less.`;
  }
  byId("k-share-note").textContent = shareNote;
  byId("k-split").replaceChildren(...TIERS.filter(t => tierShare(t) > 0).map(t => {
    const seg = el("span", { title: `${TIER_LABEL[t]} ${pct(tierShare(t))}` });
    seg.style.flex = tierShare(t); seg.style.background = css(t);
    return seg;
  }));

  byId("k-calls").textContent = fmt(calls);
  byId("k-calls-note").textContent = calls ? `${pct((tierCalls("medium") + tierCalls("low")) / calls)} on cheaper tiers` : "";
  byId("k-rate").textContent = calls ? (closedAic / calls).toFixed(1) : "-";
  byId("k-rate-note").textContent = p?.calls ? `${(p.aic / p.calls).toFixed(1)} on high tier` : "";

  const detailed = rows.filter(r => r.initiator !== "unknown");
  const detailedAic = totalOf(detailed, "aic"), detailedCalls = totalOf(detailed, "calls");
  byId("k-prompts").textContent = prompts ? fmt(prompts) : "-";
  byId("k-prompts-note").textContent = prompts
    ? `${(detailedAic / prompts).toFixed(1)} AIC and ${(detailedCalls / prompts).toFixed(1)} model calls per prompt` : "";
  const premium = totalOf(rows, "premium");
  byId("k-premium").textContent = premium ? fmt(premium) : "-";
  byId("k-premium-note").textContent = premium ? `${(total / premium).toFixed(1)} AIC per premium request` : "";
  const input = totalOf(rows, "in");
  byId("k-cache").textContent = input ? pct(totalOf(rows, "cache") / input) : "-";
  byId("k-cache-note").textContent = input ? `Saved ${fmt(totalOf(rows, "saved"))} AIC vs paying the input price` : "";
  const sub = rows.filter(r => r.initiator === "sub-agent");
  byId("k-sub").textContent = total > 0 ? pct(totalOf(sub, "aic") / total) : "-";
  byId("k-sub-note").textContent = `${fmt(totalOf(sub, "calls"))} calls made by subagents`;
}
