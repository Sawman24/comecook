/* ==============================================================================
   COOKED - Light/Dark Theme Switcher
   ============================================================================== */

const THEME_KEY = "cooked_theme_preference";

function initTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved) {
    document.documentElement.setAttribute("data-theme", saved);
  } else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    document.documentElement.setAttribute("data-theme", "dark");
  } else {
    document.documentElement.setAttribute("data-theme", "light");
  }
  updateThemeIcon();
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "light";
  const target = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", target);
  localStorage.setItem(THEME_KEY, target);
  updateThemeIcon();
  showToast(`Switched to ${target} mode`, "info", 1500);
}

function updateThemeIcon() {
  const btn = document.getElementById("theme-toggle-btn");
  if (!btn) return;
  const current = document.documentElement.getAttribute("data-theme") || "light";
  btn.innerHTML = current === "dark" ? "☀️" : "🌙";
  btn.setAttribute("title", `Switch to ${current === "dark" ? "light" : "dark"} mode`);
}

document.addEventListener("DOMContentLoaded", initTheme);
