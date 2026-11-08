import { h, icon, spinner, nextId } from "../util.js";
import { api } from "../api.js";
import { getConfig } from "../state.js";
import { openDialog } from "./dialog.js";
import { toast, toastError } from "./toast.js";

const KEY_STATUS = {
  ok: { icon: "check", cls: "is-ok" },
  invalid: { icon: "error", cls: "is-bad" },
  unverified: { icon: "info", cls: "is-unknown" },
  missing: { icon: "key", cls: "is-missing" },
};

export async function openSettingsDialog({ onSaved } = {}) {
  const cfg = getConfig() || { models: [] };
  let settings;
  try {
    settings = await api.settings();
  } catch (err) {
    toastError(err, "Couldn't load settings");
    return null;
  }

  const keyId = nextId("key");
  const keyInput = h("input", {
    id: keyId,
    type: "password",
    class: "input input-key",
    autocomplete: "off",
    spellcheck: "false",
    autocapitalize: "off",
  });
  const revealBtn = h("button", { type: "button", class: "icon-btn input-addon", "aria-label": "Show key", "aria-pressed": "false" }, icon("eye", { size: 17 }));
  const clearBtn = h("button", { type: "button", class: "btn btn-ghost btn-sm" }, icon("trash", { size: 15 }), "Remove saved key");
  const statusEl = h("div", { class: "key-status", role: "status" });
  const pausedEl = h("p", { class: "notice notice-bad", hidden: true });

  const pickerSel = h("select", { class: "select", id: nextId("picker") });
  const judgeSel = h("select", { class: "select", id: nextId("judge") });
  const saveBtn = h("button", { type: "button", class: "btn btn-primary" }, icon("check", { size: 16 }), "Save & verify");
  const closeBtn = h("button", { type: "button", class: "btn btn-ghost" }, "Close");

  function fillModels(select, selected) {
    const available = Array.isArray(settings.available_models) ? settings.available_models : null;
    select.replaceChildren(...(cfg.models || []).map((m) => {
      const unavailable = available && !available.includes(m.id);
      const text = `${m.label}${unavailable ? " (not available for this key)" : ""}`;
      return h("option", { value: m.id, disabled: unavailable && m.id !== selected, selected: m.id === selected }, text);
    }));
    if (selected && ![...select.options].some((o) => o.value === selected)) {
      select.append(h("option", { value: selected, selected: true }, `${selected} (not in the model list)`));
    }
  }

  // The selected model's note sits under its select (notes are too long for options).
  function noteFor(select, hint) {
    const m = (cfg.models || []).find((x) => x.id === select.value);
    hint.textContent = m ? [m.id, m.note].filter(Boolean).join(" · ") : select.value;
  }
  const pickerHint = h("span", { class: "field-hint muted" });
  const judgeHint = h("span", { class: "field-hint muted" });
  pickerSel.addEventListener("change", () => noteFor(pickerSel, pickerHint));
  judgeSel.addEventListener("change", () => noteFor(judgeSel, judgeHint));

  function render() {
    keyInput.placeholder = settings.has_api_key
      ? `Saved: ${settings.api_key_hint || "••••"} — paste a new key to replace it`
      : "Paste your Gemini API key";
    clearBtn.hidden = !settings.has_api_key;
    const st = KEY_STATUS[settings.key_status] || KEY_STATUS.unverified;
    const fallback = settings.has_api_key ? "Key saved." : "No key saved — analysis waits until you add one.";
    statusEl.className = `key-status ${st.cls}`;
    statusEl.replaceChildren(icon(st.icon, { size: 16 }), h("span", null, settings.key_message || fallback));
    pausedEl.hidden = !settings.queue_paused;
    pausedEl.replaceChildren(icon("warn", { size: 16 }),
      h("span", null, `Analysis paused: ${settings.queue_paused || ""}. Saving settings resumes it.`));
    fillModels(pickerSel, settings.picker_model);
    fillModels(judgeSel, settings.judge_model);
    noteFor(pickerSel, pickerHint);
    noteFor(judgeSel, judgeHint);
  }

  async function save(patch, { verifying }) {
    saveBtn.disabled = true;
    clearBtn.disabled = true;
    const label = verifying ? "Verifying…" : "Saving…";
    saveBtn.replaceChildren(spinner(15), label);
    try {
      settings = await api.saveSettings(patch);
      keyInput.value = "";
      render();
      if (settings.key_status === "invalid") toast(settings.key_message || "That key didn't work", { kind: "error" });
      else toast("Settings saved", { kind: "success" });
      if (onSaved) onSaved(settings);
    } catch (err) {
      toastError(err, "Couldn't save settings");
    } finally {
      saveBtn.disabled = false;
      clearBtn.disabled = false;
      saveBtn.replaceChildren(icon("check", { size: 16 }), "Save & verify");
    }
  }

  revealBtn.addEventListener("click", () => {
    const show = keyInput.type === "password";
    keyInput.type = show ? "text" : "password";
    revealBtn.setAttribute("aria-pressed", String(show));
    revealBtn.setAttribute("aria-label", show ? "Hide key" : "Show key");
    revealBtn.replaceChildren(icon(show ? "eyeOff" : "eye", { size: 17 }));
  });
  clearBtn.addEventListener("click", () => save({ api_key: "" }, { verifying: false }));
  saveBtn.addEventListener("click", () => {
    const patch = { picker_model: pickerSel.value, judge_model: judgeSel.value };
    const key = keyInput.value.trim();
    if (key) patch.api_key = key;
    save(patch, { verifying: Boolean(key) });
  });
  keyInput.addEventListener("keydown", (e) => { if (e.key === "Enter") saveBtn.click(); });

  const body = h("div", { class: "settings" },
    pausedEl,
    cfg.fake_mode
      ? h("p", { class: "notice" }, icon("info", { size: 16 }), h("span", null, "Fake mode is on: analysis uses a deterministic stand-in, so no key is needed."))
      : null,
    h("div", { class: "field" },
      h("label", { class: "field-label", for: keyId }, "Gemini API key"),
      h("div", { class: "input-group" }, keyInput, revealBtn),
      statusEl,
      h("div", { class: "field-row" },
        h("span", { class: "field-hint muted" }, "Stored only in this app's local database; the full key is never sent back to the browser. Create one in Google AI Studio."),
        clearBtn)),
    h("div", { class: "field-grid" },
      h("label", { class: "field" }, h("span", { class: "field-label" }, "Picker model"), pickerSel, pickerHint),
      h("label", { class: "field" }, h("span", { class: "field-label" }, "Judge model"), judgeSel, judgeHint)),
    h("p", { class: "field-hint muted" }, "Picker finds candidate promos; Judge scores them blind."));

  render();
  const dlg = openDialog({ title: "Settings", body, footer: [closeBtn, saveBtn], className: "dialog-settings" });
  closeBtn.addEventListener("click", () => dlg.close());
  keyInput.focus();
  return dlg;
}
