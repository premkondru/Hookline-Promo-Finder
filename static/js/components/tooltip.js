// One shared tooltip for any element with a data-tip attribute ("\n" = new line).
// Shown on hover and on keyboard focus; tooltips enhance, they never gate.
import { h } from "../util.js";

let tip = null;
let current = null;

function position(target) {
  const r = target.getBoundingClientRect();
  const tr = tip.getBoundingClientRect();
  const gap = 8;
  let top = r.top - tr.height - gap;
  if (top < 8) top = r.bottom + gap;
  let left = r.left + r.width / 2 - tr.width / 2;
  left = Math.max(8, Math.min(left, window.innerWidth - tr.width - 8));
  tip.style.top = `${Math.round(top)}px`;
  tip.style.left = `${Math.round(left)}px`;
}

function show(target) {
  const text = target.getAttribute("data-tip");
  if (!text) return;
  current = target;
  // Modal dialogs live in the top layer; host the tip inside them so it isn't hidden.
  const host = target.closest("dialog[open]") || document.body;
  if (tip.parentNode !== host) host.append(tip);
  tip.replaceChildren(...text.split("\n").map((line) => h("div", { class: "tooltip-line" }, line)));
  tip.hidden = false;
  tip.style.top = "-9999px";
  tip.style.left = "-9999px";
  position(target);
}

function hide() {
  current = null;
  if (tip) tip.hidden = true;
}

export function initTooltips() {
  if (tip) return;
  tip = h("div", { class: "tooltip", role: "tooltip", hidden: true });
  document.body.append(tip);

  document.addEventListener("pointerover", (e) => {
    const el = e.target instanceof Element ? e.target.closest("[data-tip]") : null;
    if (el && el !== current) show(el);
    else if (!el && current) hide();
  });
  document.addEventListener("focusin", (e) => {
    const el = e.target instanceof Element ? e.target.closest("[data-tip]") : null;
    if (el) show(el);
    else hide();
  });
  document.addEventListener("focusout", hide);
  document.addEventListener("scroll", hide, true);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") hide(); });
  window.addEventListener("hashchange", hide);
}

export function hideTooltip() {
  hide();
}
