import { startRouter } from "./router.js";
import { loadConfig } from "./state.js";
import { mountList } from "./views/list.js";
import { mountDetail } from "./views/detail.js";
import { initTooltips } from "./components/tooltip.js";
import { h, icon, spinner, wordmark } from "./util.js";

const outlet = document.getElementById("app");

function renderBootError(err) {
  outlet.replaceChildren(h("div", { class: "page" },
    h("div", { class: "boot" },
      wordmark(),
      h("div", { class: "empty" },
        h("div", { class: "empty-art is-bad", "aria-hidden": "true" }, icon("error", { size: 30 })),
        h("h1", { class: "empty-title" }, "Can't reach the Hookline server"),
        h("p", { class: "muted" }, (err && err.message) || "Unknown error"),
        h("button", { class: "btn btn-primary", type: "button", onClick: () => location.reload() }, icon("retry", { size: 16 }), "Try again")))));
}

async function boot() {
  initTooltips();
  outlet.replaceChildren(h("div", { class: "boot" }, spinner(26)));
  try {
    await loadConfig();
  } catch (err) {
    renderBootError(err);
    return;
  }
  startRouter([
    { pattern: /^\/$/, mount: mountList },
    { pattern: /^\/promo\/(\d+)$/, mount: mountDetail },
  ], outlet);
}

boot();
