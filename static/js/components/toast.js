import { h, icon } from "../util.js";

const KIND_ICON = { info: "info", success: "check", error: "error", warn: "warn" };

/** toast("Saved", {kind: "success"}) — kind: info | success | warn | error */
// A modal <dialog> sits in the top layer above everything else, so while one is
// open its toasts render inside it (position: fixed still pins them to the viewport).
function toastHost() {
  const dlg = document.querySelector("dialog[open]");
  if (!dlg) return document.getElementById("toasts");
  let host = dlg.querySelector(":scope > .toasts");
  if (!host) {
    host = h("div", { class: "toasts", "aria-live": "polite" });
    dlg.append(host);
  }
  return host;
}

export function toast(message, { kind = "info", timeout = 4800 } = {}) {
  const host = toastHost();
  if (!host) return;
  const el = h("div", { class: ["toast", `toast-${kind}`], role: kind === "error" ? "alert" : "status" },
    icon(KIND_ICON[kind] || "info", { size: 18 }),
    h("span", { class: "toast-text" }, message),
    h("button", {
      class: "toast-close",
      type: "button",
      "aria-label": "Dismiss",
      onClick: () => dismiss(),
    }, icon("close", { size: 14 })));
  let timer = null;
  function dismiss() {
    clearTimeout(timer);
    el.classList.add("is-leaving");
    setTimeout(() => el.remove(), 220);
  }
  host.append(el);
  if (timeout) timer = setTimeout(dismiss, kind === "error" ? timeout * 1.6 : timeout);
  return dismiss;
}

export function toastError(err, prefix) {
  const msg = (err && err.message) || String(err);
  toast(prefix ? `${prefix}: ${msg}` : msg, { kind: "error" });
}
