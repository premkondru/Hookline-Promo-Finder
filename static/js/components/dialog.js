// Modal dialogs on the native <dialog> element: showModal() makes the rest of the
// page inert (so focus stays inside), Esc closes, focus returns to the opener.
import { h, icon, nextId } from "../util.js";

export function openDialog({ title, body, footer, className, onClose, wide = false }) {
  const titleId = nextId("dlg-title");
  const opener = document.activeElement;
  const closeBtn = h("button", { class: "icon-btn dialog-close", type: "button", "aria-label": "Close" },
    icon("close", { size: 18 }));
  const panel = h("div", { class: "dialog-panel" },
    h("header", { class: "dialog-head" }, h("h2", { id: titleId, class: "dialog-title" }, title), closeBtn),
    h("div", { class: "dialog-body" }, body),
    footer ? h("footer", { class: "dialog-foot" }, footer) : null);
  const dlg = h("dialog", { class: ["dialog", wide && "dialog-wide", className], "aria-labelledby": titleId }, panel);

  closeBtn.addEventListener("click", () => dlg.close());
  // A click whose target is the <dialog> itself landed on the backdrop.
  dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
  dlg.addEventListener("close", () => {
    dlg.remove();
    if (onClose) onClose();
    if (opener && opener.isConnected && typeof opener.focus === "function") opener.focus();
  });

  document.body.append(dlg);
  dlg.showModal();
  const autofocus = panel.querySelector("[autofocus]");
  if (autofocus) autofocus.focus();
  return { el: dlg, panel, close: () => dlg.close() };
}

/** Resolves true when confirmed, false when cancelled/closed. */
export function confirmDialog({ title, message, confirmLabel = "Delete", danger = true }) {
  return new Promise((resolve) => {
    let result = false;
    const cancel = h("button", { class: "btn btn-ghost", type: "button", autofocus: true }, "Cancel");
    const ok = h("button", { class: ["btn", danger ? "btn-danger" : "btn-primary"], type: "button" },
      danger ? icon("trash", { size: 16 }) : null, confirmLabel);
    const dlg = openDialog({
      title,
      body: h("p", { class: "confirm-text" }, message),
      footer: [cancel, ok],
      className: "dialog-confirm",
      onClose: () => resolve(result),
    });
    cancel.addEventListener("click", () => dlg.close());
    ok.addEventListener("click", () => { result = true; dlg.close(); });
  });
}
