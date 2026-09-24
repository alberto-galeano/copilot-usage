const SVG = "http://www.w3.org/2000/svg";

export const byId = id => document.getElementById(id);

export function el(tag, attrs = {}, text) {
  const node = tag === "svg" || attrs.svg ? document.createElementNS(SVG, tag) : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) if (k !== "svg") node.setAttribute(k, v);
  if (text !== undefined) node.textContent = text;
  return node;
}
export const s = (tag, attrs, text) => el(tag, { ...attrs, svg: 1 }, text);
export function swatch(color) { const sw = el("span", { class: "swatch" }); sw.style.background = color; return sw; }

export function clickable(node, action) {
  node.classList.add("pick");
  if (node.tagName !== "TR") node.setAttribute("role", "button");
  node.addEventListener("click", action);
  node.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); action(); } });
}

// One tab stop per chart, arrow keys move between its marks.
export function roving(svg, stride = 1) {
  const stops = [...svg.querySelectorAll("[tabindex]")];
  stops.forEach((node, i) => node.setAttribute("tabindex", i ? "-1" : "0"));
  svg.addEventListener("keydown", e => {
    const step = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: stride, ArrowUp: -stride }[e.key];
    const next = stops[stops.indexOf(e.target) + step];
    if (!next) return;
    e.preventDefault();
    next.focus();
  });
}
