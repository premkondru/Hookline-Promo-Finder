import { h, icon, spinner, nextId, plural } from "../util.js";
import { api } from "../api.js";
import { openDialog } from "./dialog.js";
import { toast, toastError } from "./toast.js";

const ACCEPT = [".txt", ".zip"];
const STATUS = {
  added: { icon: "check", label: "Added" },
  duplicate: { icon: "copy", label: "Duplicate" },
  invalid: { icon: "error", label: "Not added" },
};

const sizeLabel = (bytes) => (bytes < 1024 ? `${bytes} B` : bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`);

export function openUploadDialog({ shows = [], onUploaded } = {}) {
  let files = [];
  let busy = false;

  const inputId = nextId("upload-input");
  const listId = nextId("shows");
  const input = h("input", { id: inputId, type: "file", accept: ACCEPT.join(","), multiple: true, class: "sr-only", tabindex: -1 });
  const dropzone = h("button", { type: "button", class: "dropzone" },
    h("span", { class: "dropzone-icon" }, icon("upload", { size: 26 })),
    h("strong", null, "Drop episode scripts here"),
    h("span", { class: "muted" }, ".txt screenplays or a .zip of them — or click to browse"));
  const fileList = h("ul", { class: "file-list", "aria-label": "Selected files" });
  const showInput = h("input", {
    id: nextId("show"),
    type: "text",
    class: "input",
    list: listId,
    maxlength: 200,
    placeholder: "Optional — a zip uses its folder name",
    autocomplete: "off",
  });
  const datalist = h("datalist", { id: listId }, shows.map((sh) => h("option", { value: sh.title })));
  const results = h("section", { class: "upload-results", hidden: true, "aria-live": "polite" });
  const uploadBtn = h("button", { class: "btn btn-primary", type: "button", disabled: true }, icon("upload", { size: 16 }), "Upload");
  const closeBtn = h("button", { class: "btn btn-ghost", type: "button" }, "Close");

  function renderFiles() {
    fileList.replaceChildren(...files.map((file, i) =>
      h("li", { class: "file-item" },
        icon(file.name.toLowerCase().endsWith(".zip") ? "copy" : "file", { size: 16 }),
        h("span", { class: "file-name" }, file.name),
        h("span", { class: "file-size muted" }, sizeLabel(file.size)),
        h("button", {
          class: "icon-btn icon-btn-sm",
          type: "button",
          "aria-label": `Remove ${file.name}`,
          onClick: () => { files.splice(i, 1); renderFiles(); },
        }, icon("close", { size: 14 })))));
    fileList.hidden = files.length === 0;
    uploadBtn.disabled = busy || files.length === 0;
  }

  function addFiles(fileListLike) {
    const skipped = [];
    for (const file of Array.from(fileListLike || [])) {
      const lower = file.name.toLowerCase();
      if (!ACCEPT.some((ext) => lower.endsWith(ext))) { skipped.push(file.name); continue; }
      if (files.some((f) => f.name === file.name && f.size === file.size)) continue;
      files.push(file);
    }
    if (skipped.length) toast(`Skipped ${skipped.join(", ")} — only .txt or .zip files`, { kind: "warn" });
    renderFiles();
  }

  function renderResults(res) {
    const rows = (res.results || []).map((r) => {
      const meta = STATUS[r.status] || STATUS.invalid;
      return h("li", { class: ["result-item", `result-${r.status}`] },
        h("span", { class: "result-icon" }, icon(meta.icon, { size: 16 })),
        h("div", { class: "result-body" },
          h("div", { class: "result-line" },
            h("span", { class: "result-file" }, r.filename),
            h("span", { class: "result-status" }, meta.label)),
          r.message ? h("p", { class: "result-msg muted" }, r.message) : null));
    });
    const summary = [
      plural(res.added ?? 0, "added", "added"),
      plural(res.duplicates ?? 0, "duplicate"),
      `${res.invalid ?? 0} not added`,
    ].join(" · ");
    results.replaceChildren(h("h3", { class: "results-title" }, summary), h("ul", { class: "result-list" }, rows));
    results.hidden = false;
  }

  async function doUpload() {
    if (!files.length || busy) return;
    busy = true;
    uploadBtn.disabled = true;
    uploadBtn.replaceChildren(spinner(15), "Uploading…");
    try {
      const res = await api.upload(files, showInput.value.trim());
      renderResults(res);
      files = [];
      renderFiles();
      if (res.added) toast(`${plural(res.added, "episode")} queued for analysis`, { kind: "success" });
      if (onUploaded) onUploaded(res);
    } catch (err) {
      toastError(err, "Upload failed");
    } finally {
      busy = false;
      uploadBtn.replaceChildren(icon("upload", { size: 16 }), "Upload");
      renderFiles();
    }
  }

  dropzone.addEventListener("click", () => input.click());
  for (const ev of ["dragenter", "dragover"]) {
    dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add("is-over"); });
  }
  for (const ev of ["dragleave", "dragend"]) {
    dropzone.addEventListener(ev, () => dropzone.classList.remove("is-over"));
  }
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("is-over");
    addFiles(e.dataTransfer && e.dataTransfer.files);
  });
  input.addEventListener("change", () => { addFiles(input.files); input.value = ""; });
  uploadBtn.addEventListener("click", doUpload);

  const body = h("div", { class: "upload" },
    dropzone, input, fileList,
    h("label", { class: "field" },
      h("span", { class: "field-label" }, "Show title"),
      showInput, datalist,
      h("span", { class: "field-hint muted" }, "Loose .txt files without a title go under “Untitled show”. Episodes already in the app are skipped by content, not filename.")),
    results);

  renderFiles();
  const dlg = openDialog({ title: "Upload episodes", body, footer: [closeBtn, uploadBtn], className: "dialog-upload" });
  closeBtn.addEventListener("click", () => dlg.close());
  dropzone.focus();
  return dlg;
}
