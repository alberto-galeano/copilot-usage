// A classic script in <head> so the saved theme applies before first paint instead of flashing in late.
document.documentElement.dataset.theme = "hud";
try { document.documentElement.dataset.theme = localStorage.getItem("theme") || "hud"; } catch {}
