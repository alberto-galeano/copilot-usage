import { byId, el } from "./dom.js";

const tip = byId("tip");

function showTip(evt, head, lines) {
  tip.replaceChildren(el("div", { class: "head" }, head));
  for (const { color, value, label } of lines) {
    const row = el("div", { class: "row" });
    const key = el("span", { class: "key" }); key.style.background = color || "transparent";
    row.append(key, el("b", {}, value), el("span", {}, label));
    tip.append(row);
  }
  tip.style.display = "block";
  const box = evt.target.getBoundingClientRect();
  const x = evt.clientX || box.right, y = evt.clientY || box.top;
  tip.style.left = Math.min(x + 14, innerWidth - tip.offsetWidth - 8) + "px";
  tip.style.top = Math.max(8, y - tip.offsetHeight - 10) + "px";
}

export function hideTip() { tip.style.display = "none"; }

export function hoverable(node, head, lines) {
  node.setAttribute("tabindex", "0");
  node.addEventListener("pointermove", e => showTip(e, head, lines));
  node.addEventListener("focus", e => showTip(e, head, lines));
  node.addEventListener("pointerleave", hideTip);
  node.addEventListener("blur", hideTip);
}
