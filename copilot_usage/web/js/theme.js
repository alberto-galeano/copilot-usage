import { byId, el } from "./dom.js";
import { css } from "./format.js";

const THEMES = [
  { id: "hud", label: "Neon HUD", note: "futuristic" },
  { id: "synthwave", label: "Synthwave", note: "retro neon" },
  { id: "terminal", label: "Terminal", note: "phosphor" },
  { id: "ember", label: "Ember", note: "warm" },
  { id: "blueprint", label: "Blueprint", note: "technical" },
  { id: "nord", label: "Nord", note: "calm" },
  { id: "graphite", label: "Graphite", note: "minimal" },
  { id: "brutalist-dark", label: "Brutalist Dark", note: "bold" },
  { id: "daylight", label: "Daylight", note: "clean" },
  { id: "paper", label: "Paper", note: "minimal" },
  { id: "brutalist", label: "Brutalist", note: "bold" },
  { id: "candy", label: "Candy", note: "playful" },
];
const root = document.documentElement;

function setTheme(id) {
  root.dataset.theme = id;
  try { localStorage.setItem("theme", id); } catch {}
}

function renderThemes() {
  byId("themes").replaceChildren(...THEMES.map(t => {
    const card = el("label", { class: "theme", "data-theme": t.id });
    const input = el("input", { type: "radio", name: "theme", value: t.id });
    input.checked = t.id === root.dataset.theme;
    input.addEventListener("change", () => setTheme(t.id));
    const mini = el("div", { class: "mini" });
    [["high", 90], ["high", 35], ["medium", 20], ["low", 55], ["high", 70]].forEach(([tier, height]) => {
      const bar = el("i");
      bar.style.color = css(tier); bar.style.height = height + "%";
      mini.append(bar);
    });
    const name = el("div", { class: "name" }, t.label);
    name.append(el("small", {}, t.note));
    card.append(input, mini, name);
    return card;
  }));
}

export function initSettings() {
  if (!THEMES.some(t => t.id === root.dataset.theme)) setTheme("hud");
  const settings = byId("settings");
  byId("open-settings").addEventListener("click", () => { renderThemes(); settings.showModal(); settings.querySelector("input:checked").focus(); });
  settings.addEventListener("click", e => { if (e.target === settings) settings.close(); });
}
