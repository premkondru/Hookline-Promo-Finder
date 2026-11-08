// List page: ranked promos, processing tray, upload/settings entry points.
import { h, s, icon, spinner, wordmark, fmtLength, fmtScore, plural, epLabel, humanize } from "../util.js";
import { api } from "../api.js";
import { getConfig, dimensions, toneVars, prefs } from "../state.js";
import { openUploadDialog } from "../components/upload.js";
import { openSettingsDialog } from "../components/settings.js";
import { confirmDialog } from "../components/dialog.js";
import { toast, toastError } from "../components/toast.js";
import { navigate } from "../router.js";

const POLL_MS = 2000;
const TRAY_PREVIEW = 12;

function sortOptions() {
  return [
    { key: "composite", label: "Composite score" },
    ...dimensions().map((d) => ({ key: d.key, label: d.label })),
    { key: "episode", label: "Episode #" },
    { key: "duration", label: "Duration" },
  ];
}

const defaultDir = (key) => (key === "episode" ? "asc" : "desc");

function sortValue(p, key) {
  if (key === "composite") return p.composite;
  if (key === "episode") return p.episode_number;
  if (key === "duration") return p.duration_sec;
  const v = p.scores ? p.scores[key] : null;
  return v == null ? null : Number(v);
}

function sortPromos(promos, key, dir) {
  const mul = dir === "asc" ? 1 : -1;
  const tiebreak = (a, b) =>
    (Number(b.composite ?? -1) - Number(a.composite ?? -1)) ||
    (Number(a.episode_number ?? 1e9) - Number(b.episode_number ?? 1e9)) ||
    (a.id - b.id);
  return [...promos].sort((a, b) => {
    const va = sortValue(a, key);
    const vb = sortValue(b, key);
    if (va == null && vb == null) return tiebreak(a, b);
    if (va == null) return 1;
    if (vb == null) return -1;
    if (va !== vb) return (va - vb) * mul;
    return tiebreak(a, b);
  });
}

/* ------------------------------------------------------------ row pieces */

function compositeRing(value) {
  const r = 21;
  const c = 2 * Math.PI * r;
  const frac = Math.max(0, Math.min(1, Number(value ?? 0) / 10));
  return h("div", { class: "score-ring", role: "img", "aria-label": `Composite score ${fmtScore(value)} out of 10` },
    s("svg", { viewBox: "0 0 52 52", width: 52, height: 52, "aria-hidden": "true" },
      s("circle", { class: "score-ring-track", cx: 26, cy: 26, r }),
      s("circle", {
        class: "score-ring-fill",
        cx: 26,
        cy: 26,
        r,
        "stroke-dasharray": `${(c * frac).toFixed(2)} ${c.toFixed(2)}`,
        transform: "rotate(-90 26 26)",
      })),
    h("span", { class: "score-ring-value" }, fmtScore(value)));
}

// One horizontal bar per dimension (one series → one hue). When the list is sorted
// by a dimension, that bar keeps the accent and the rest fall back to gray.
function miniBars(p, sortKey) {
  const dims = dimensions();
  const emphasis = dims.some((d) => d.key === sortKey) ? sortKey : null;
  const label = dims.map((d) => `${d.label} ${fmtScore(p.scores?.[d.key], 0)}`).join(", ");
  return h("div", { class: ["minibars", emphasis && "has-emphasis"], role: "img", "aria-label": `Scores: ${label}` },
    dims.map((d) => {
      const v = p.scores ? Number(p.scores[d.key]) : NaN;
      const ok = Number.isFinite(v);
      return h("div", {
        class: ["minibar", emphasis === d.key && "is-emphasis"],
        "data-tip": d.question ? `${d.label}: ${ok ? `${fmtScore(v, 0)}/10` : "no score"}\n${d.question}` : `${d.label}: ${ok ? `${fmtScore(v, 0)}/10` : "no score"}`,
        "aria-hidden": "true",
      },
      h("span", { class: "minibar-label" }, d.label),
      h("span", { class: "minibar-track" },
        h("span", { class: "minibar-fill", style: { width: `${ok ? Math.max(3, v * 10) : 0}%` } })),
      h("span", { class: "minibar-value" }, ok ? fmtScore(v, 0) : "—"));
    }));
}

// Info-level flags (hook timing, flash-forward, repaired) are notes, not problems:
// only warnings and errors earn a badge on the row.
function flagsBadge(flags) {
  const problems = (flags || []).filter((f) => f.level === "error" || f.level === "warn");
  if (!problems.length) return null;
  const level = problems.some((f) => f.level === "error") ? "error" : "warn";
  const tip = problems.map((f) => `${f.level === "error" ? "✕" : "!"}  ${f.message}`).join("\n");
  return h("button", {
    class: ["flag-badge", `flag-${level}`],
    type: "button",
    "data-tip": tip,
    "aria-label": `${plural(problems.length, "quality flag")}: ${problems.map((f) => f.message).join("; ")}`,
  }, icon(level === "error" ? "error" : "warn", { size: 15 }), String(problems.length));
}

function segmentsText(p) {
  const segs = p.segments || [];
  if (!segs.length) return "no segments";
  return segs.map((seg) => `${seg.start} → ${seg.end}`).join("  +  ");
}

/* ------------------------------------------------------------ view */

export function mountList(outlet, _params, query) {
  const cfg = getConfig();
  let alive = true;
  let pollTimer = 0;
  let lastSig = "";
  let lastTraySig = "";
  let trayExpanded = false;

  const state = {
    shows: [],
    promos: [],
    episodes: [],
    waitingForKey: false,
    pausedReason: null,
    loaded: false,
    show: prefs.get("show", ""),
    sort: prefs.get("sort", "composite"),
    dir: prefs.get("dir", ""),
  };
  // Deep links: #/?sort=hook&dir=asc&show=<title>
  if (query.has("sort")) { state.sort = query.get("sort"); state.dir = query.get("dir") || ""; }
  if (query.has("show")) state.show = query.get("show");
  if (!sortOptions().some((o) => o.key === state.sort)) state.sort = "composite";
  if (state.dir !== "asc" && state.dir !== "desc") state.dir = defaultDir(state.sort);

  /* header controls */
  const showSel = h("select", { class: "select select-compact", "aria-label": "Show" });
  const sortSel = h("select", { class: "select select-compact", "aria-label": "Sort by" },
    sortOptions().map((o) => h("option", { value: o.key, selected: o.key === state.sort }, o.label)));
  const dirBtn = h("button", { class: "icon-btn", type: "button" });
  const uploadBtn = h("button", { class: "btn btn-primary", type: "button" }, icon("upload", { size: 16 }), "Upload");
  const settingsBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Settings", "data-tip": "Settings — API key & models" }, icon("settings", { size: 19 }));
  const exportMenu = h("details", { class: "menu" },
    h("summary", { class: "icon-btn", "aria-label": "Export ranked list", "data-tip": "Export ranked list" }, icon("download", { size: 18 })),
    h("div", { class: "menu-panel", role: "menu" }));

  const header = h("header", { class: "topbar" },
    h("div", { class: "topbar-inner" },
      wordmark(),
      cfg && cfg.fake_mode ? h("span", { class: "pill pill-warn", "data-tip": "Analysis uses a deterministic fake model — not Gemini" }, "Fake mode") : null,
      h("div", { class: "topbar-spacer" }),
      h("div", { class: "topbar-controls" },
        h("label", { class: "control control-show" }, h("span", { class: "control-label" }, "Show"), showSel),
        h("label", { class: "control" }, h("span", { class: "control-label" }, "Sort"), sortSel),
        dirBtn,
        exportMenu,
        settingsBtn,
        uploadBtn)));

  const titleEl = h("h1", { class: "page-title" }, "Promos");
  const subtitleEl = h("p", { class: "page-subtitle" });
  const banner = h("div", { class: "banner", hidden: true, role: "status" });
  const tray = h("section", { class: "tray", hidden: true, "aria-label": "Processing" });
  const listEl = h("div", { class: "promo-list", role: "list" });
  const page = h("div", { class: "page page-list" },
    header,
    h("div", { class: "container" },
      h("div", { class: "page-head" }, titleEl, subtitleEl),
      banner,
      tray,
      listEl));
  outlet.append(page);
  document.body.dataset.view = "list";

  /* ------------------------------------------------------------ render */
  function renderDir() {
    const asc = state.dir === "asc";
    dirBtn.replaceChildren(icon(asc ? "arrowUp" : "arrowDown", { size: 18 }));
    const label = asc ? "Ascending — click for descending" : "Descending — click for ascending";
    dirBtn.setAttribute("aria-label", `Sort direction: ${label}`);
    dirBtn.setAttribute("data-tip", label);
  }

  function renderShows() {
    const shows = state.shows;
    if (state.show && !shows.some((sh) => sh.title === state.show)) state.show = "";
    showSel.replaceChildren(
      h("option", { value: "", selected: !state.show }, "All shows"),
      ...shows.map((sh) => h("option", { value: sh.title, selected: sh.title === state.show }, `${sh.title} (${sh.promos})`)));
    showSel.closest(".control").hidden = shows.length <= 1;
  }

  function renderExport() {
    const panel = exportMenu.querySelector(".menu-panel");
    panel.replaceChildren(
      h("a", { class: "menu-item", role: "menuitem", href: api.exportUrl("csv", state.show), download: "" }, icon("file", { size: 16 }), "CSV"),
      h("a", { class: "menu-item", role: "menuitem", href: api.exportUrl("md", state.show), download: "" }, icon("file", { size: 16 }), "Markdown"));
  }

  function renderHead() {
    const n = state.promos.length;
    const opt = sortOptions().find((o) => o.key === state.sort);
    const scope = state.show || (state.shows.length === 1 ? state.shows[0].title : state.shows.length ? "all shows" : "");
    subtitleEl.replaceChildren(
      h("span", null, plural(n, "promo")),
      scope ? h("span", { class: "dot-sep" }, scope) : null,
      h("span", { class: "dot-sep" }, `sorted by ${opt ? opt.label.toLowerCase() : state.sort}`));
  }

  function renderBanner() {
    const queued = state.episodes.filter((e) => e.status === "queued").length;
    banner.classList.remove("is-bad");
    if (state.pausedReason) {
      // A bad key or exhausted quota paused the queue; saving settings or Retry resumes it.
      banner.hidden = false;
      banner.classList.add("is-bad");
      banner.replaceChildren(
        icon("warn", { size: 18 }),
        h("span", null, `Analysis paused: ${state.pausedReason}`),
        h("button", { class: "btn btn-sm", type: "button", onClick: () => openSettings() }, "Open settings"));
    } else if (state.waitingForKey && queued > 0 && !(cfg && cfg.fake_mode)) {
      banner.hidden = false;
      banner.replaceChildren(
        icon("key", { size: 18 }),
        h("span", null, `${plural(queued, "episode")} waiting — add a Gemini key to start analysis.`),
        h("button", { class: "btn btn-sm", type: "button", onClick: () => openSettings() }, "Add key"));
    } else {
      banner.hidden = true;
      banner.replaceChildren();
    }
  }

  function trayChip(ep) {
    const status = ep.status === "queued" && state.pausedReason ? "paused"
      : ep.status === "queued" && state.waitingForKey ? "waiting" : ep.status;
    const label = {
      queued: "Queued",
      waiting: "Waiting for key",
      paused: "Paused",
      analyzing: "Analyzing",
      failed: "Failed",
    }[status] || ep.status;
    const lead = status === "analyzing" ? spinner(13)
      : status === "failed" ? icon("error", { size: 14 })
        : icon("info", { size: 14 });
    const chip = h("div", {
      class: ["chip", `chip-${status}`],
      role: "listitem",
      "data-tip": ep.status === "failed" ? `${ep.source_filename || ""}\n${ep.error || "Analysis failed"}` : (ep.source_filename || ""),
    },
    lead,
    h("span", { class: "chip-ep" }, epLabel(ep)),
    h("span", { class: "chip-status" }, label));
    if (ep.status === "failed") {
      chip.append(
        h("button", {
          class: "chip-btn",
          type: "button",
          "aria-label": `Retry ${epLabel(ep)}`,
          "data-tip": "Retry analysis",
          onClick: async () => {
            try {
              await api.retryEpisode(ep.id);
              toast(`${epLabel(ep)} re-queued`, { kind: "success" });
              refresh(true);
            } catch (err) { toastError(err, "Retry failed"); }
          },
        }, icon("retry", { size: 14 })),
        h("button", {
          class: "chip-btn",
          type: "button",
          "aria-label": `Delete ${epLabel(ep)}`,
          "data-tip": "Delete episode",
          onClick: async () => {
            const ok = await confirmDialog({
              title: "Delete episode?",
              message: `Delete ${ep.episode_label || epLabel(ep)}${ep.show_title ? ` of “${ep.show_title}”` : ""}? You can re-upload it later.`,
            });
            if (!ok) return;
            try {
              await api.deleteEpisode(ep.id);
              toast(`${epLabel(ep)} deleted`, { kind: "success" });
              refresh(true);
            } catch (err) { toastError(err, "Delete failed"); }
          },
        }, icon("trash", { size: 14 })));
    }
    return chip;
  }

  function renderTray() {
    const eps = state.episodes;
    const sig = JSON.stringify([eps.map((e) => [e.id, e.status, e.error]), state.waitingForKey, state.pausedReason, trayExpanded]);
    if (sig === lastTraySig) return;
    lastTraySig = sig;
    if (!eps.length) {
      tray.hidden = true;
      tray.replaceChildren();
      return;
    }
    const counts = { analyzing: 0, queued: 0, failed: 0 };
    for (const e of eps) counts[e.status] = (counts[e.status] || 0) + 1;
    const parts = [];
    if (counts.analyzing) parts.push(`${counts.analyzing} analyzing`);
    if (counts.queued) parts.push(`${counts.queued} queued`);
    if (counts.failed) parts.push(`${counts.failed} failed`);
    const order = { failed: 0, analyzing: 1, queued: 2 };
    const sorted = [...eps].sort((a, b) => (order[a.status] ?? 3) - (order[b.status] ?? 3) || (a.episode_number ?? 0) - (b.episode_number ?? 0));
    const shown = trayExpanded ? sorted : sorted.slice(0, TRAY_PREVIEW);
    const more = sorted.length - shown.length;
    tray.hidden = false;
    tray.replaceChildren(
      h("div", { class: "tray-head" },
        counts.analyzing ? spinner(14) : icon("info", { size: 15 }),
        h("h2", { class: "tray-title" }, "Processing"),
        h("span", { class: "muted" }, parts.join(" · "))),
      h("div", { class: "chips", role: "list" },
        shown.map(trayChip),
        more > 0
          ? h("button", { class: "chip chip-more", type: "button", onClick: () => { trayExpanded = true; lastTraySig = ""; renderTray(); } }, `+${more} more`)
          : null,
        trayExpanded && sorted.length > TRAY_PREVIEW
          ? h("button", { class: "chip chip-more", type: "button", onClick: () => { trayExpanded = false; lastTraySig = ""; renderTray(); } }, "Show less")
          : null));
  }

  function renderRow(p, position) {
    const rowTitleId = `row-title-${p.id}`;
    const del = h("button", {
      class: "icon-btn row-delete",
      type: "button",
      "aria-label": `Delete promo for ${p.episode_label || epLabel(p)}`,
      "data-tip": "Delete promo and its episode",
    }, icon("trash", { size: 17 }));
    del.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const ok = await confirmDialog({
        title: "Delete promo?",
        message: `Delete this promo and ${p.episode_label || epLabel(p)}? You can re-upload the episode later.`,
      });
      if (!ok) return;
      try {
        await api.deletePromo(p.id);
        toast(`${p.episode_label || epLabel(p)} deleted`, { kind: "success" });
        refresh(true);
      } catch (err) { toastError(err, "Delete failed"); }
    });

    const dimKey = dimensions().some((d) => d.key === state.sort) ? state.sort : null;
    const dimMeta = dimKey ? dimensions().find((d) => d.key === dimKey) : null;

    // The title is the real link (keyboard, middle-click); the rest of the row is a
    // mouse convenience that ignores clicks on its own controls.
    const onRowClick = (e) => {
      if (e.target.closest("a, button, summary, input, select, label")) return;
      if (window.getSelection && String(window.getSelection()).length) return;
      navigate(`/promo/${p.id}`);
    };
    return h("article", { class: "row", role: "listitem", style: toneVars(p.tone), "aria-labelledby": rowTitleId, onClick: onRowClick },
      h("div", { class: "row-pos", "aria-hidden": "true" }, String(position)),
      h("div", { class: "row-main" },
        h("div", { class: "row-kicker" },
          h("span", { class: "ep-badge" }, epLabel(p)),
          p.post_first ? h("span", { class: "ribbon", "data-tip": "Top-scoring promos from the first third of the series with no spoiler, ad-policy or spec flags" }, icon("spark", { size: 12 }), "Post first") : null,
          p.hook_type ? h("span", { class: "tag", "data-tip": "Hook type" }, humanize(p.hook_type)) : null),
        h("h3", { class: "row-title", id: rowTitleId },
          h("a", { class: "row-link", href: `#/promo/${p.id}` }, p.title || "Untitled promo")),
        p.hook ? h("p", { class: "row-hook" }, p.hook) : null,
        h("p", { class: "row-meta" },
          h("span", null, fmtLength(p.duration_sec)),
          h("span", { class: "dot-sep" }, plural((p.segments || []).length, "segment")),
          h("span", { class: "dot-sep mono" }, segmentsText(p)))),
      h("div", { class: "row-scores" }, miniBars(p, state.sort)),
      h("div", { class: "row-side" },
        h("div", { class: "row-composite" },
          compositeRing(p.composite),
          dimMeta
            ? h("span", { class: "row-dimscore" }, `${dimMeta.label} ${fmtScore(p.scores?.[dimKey], 0)}`)
            : h("span", { class: "row-dimscore muted" }, "composite")),
        h("div", { class: "row-actions" }, flagsBadge(p.flags), del)));
  }

  function renderList(force) {
    const sorted = sortPromos(state.promos, state.sort, state.dir);
    const sig = JSON.stringify([state.sort, state.dir, sorted.map((p) => [p.id, p.composite, p.rank, p.post_first, p.flags?.length, p.title])]);
    if (!force && sig === lastSig) return;
    lastSig = sig;
    if (!state.loaded) {
      listEl.replaceChildren(h("div", { class: "empty" }, spinner(22), h("p", null, "Loading promos…")));
      return;
    }
    if (!sorted.length) {
      const pending = state.episodes.filter((e) => e.status === "queued" || e.status === "analyzing").length;
      const needsKey = pending > 0 && state.waitingForKey && !(cfg && cfg.fake_mode);
      const paused = pending > 0 && Boolean(state.pausedReason);
      let art = "upload", title = "No promos yet";
      let text = "Upload episodes (.txt or .zip) and Hookline will find the best promo in each.";
      let action = h("button", { class: "btn btn-primary", type: "button", onClick: openUpload }, icon("upload", { size: 16 }), "Upload episodes");
      if (needsKey) {
        art = "key"; title = "Ready to analyze";
        text = `${plural(pending, "episode")} queued. Add a Gemini key and Hookline will find the best promo in each; they appear here as they finish.`;
        action = h("button", { class: "btn btn-primary", type: "button", onClick: () => openSettings() }, icon("key", { size: 16 }), "Add Gemini key");
      } else if (paused) {
        art = "warn"; title = "Analysis paused";
        text = `${state.pausedReason} Fix it in Settings to resume the ${plural(pending, "queued episode")}.`;
        action = h("button", { class: "btn btn-primary", type: "button", onClick: () => openSettings() }, "Open settings");
      } else if (pending > 0) {
        art = "spark"; title = "Promos are on the way"; action = null;
        text = `Analyzing ${plural(pending, "episode")}; promos appear here as each one finishes.`;
      }
      listEl.replaceChildren(h("div", { class: "empty" },
        h("div", { class: "empty-art", "aria-hidden": "true" }, icon(art, { size: 30 })),
        h("h2", { class: "empty-title" }, title),
        h("p", { class: "muted" }, text),
        action));
      return;
    }
    listEl.replaceChildren(...sorted.map((p, i) => renderRow(p, i + 1)));
  }

  function renderAll(force = false) {
    renderDir();
    renderShows();
    renderExport();
    renderHead();
    renderBanner();
    renderTray();
    renderList(force);
  }

  /* ------------------------------------------------------------ data */
  let inflight = null;
  let pending = false;
  let pendingForce = false;
  async function load() {
    const [shows, promos, episodes] = await Promise.all([api.shows(), api.promos(state.show), api.episodes()]);
    if (!alive) return;
    state.shows = shows.shows || [];
    state.promos = promos.promos || [];
    state.episodes = episodes.episodes || [];
    state.waitingForKey = Boolean(episodes.waiting_for_key);
    state.pausedReason = episodes.paused_reason || null;
    state.loaded = true;
  }

  function refresh(force = false) {
    if (inflight) {
      // A filter change or mutation arrived mid-fetch: run once more afterwards.
      pending = true;
      pendingForce = pendingForce || force;
      return inflight;
    }
    inflight = (async () => {
      try {
        await load();
        if (alive) renderAll(force);
      } catch (err) {
        if (alive) {
          if (!state.loaded) {
            state.loaded = true;
            listEl.replaceChildren(h("div", { class: "empty" },
              h("div", { class: "empty-art is-bad", "aria-hidden": "true" }, icon("error", { size: 30 })),
              h("h2", { class: "empty-title" }, "Couldn't load promos"),
              h("p", { class: "muted" }, err.message),
              h("button", { class: "btn", type: "button", onClick: () => { state.loaded = false; refresh(true); } }, icon("retry", { size: 16 }), "Try again")));
          } else {
            toastError(err, "Refresh failed");
          }
        }
      } finally {
        inflight = null;
        if (pending && alive) {
          const again = pendingForce;
          pending = false;
          pendingForce = false;
          refresh(again);
        } else {
          schedulePoll();
        }
      }
    })();
    return inflight;
  }

  function schedulePoll() {
    clearTimeout(pollTimer);
    if (!alive) return;
    // Poll only while work can actually progress (not while waiting for a key or paused).
    const stalled = state.waitingForKey || Boolean(state.pausedReason);
    const active = state.episodes.some((e) => e.status === "analyzing" || (e.status === "queued" && !stalled));
    if (active) pollTimer = setTimeout(() => refresh(), POLL_MS);
  }

  /* ------------------------------------------------------------ actions */
  function openUpload() {
    openUploadDialog({ shows: state.shows, onUploaded: () => refresh(true) });
  }
  function openSettings() {
    openSettingsDialog({ onSaved: () => refresh(true) });
  }

  showSel.addEventListener("change", () => {
    state.show = showSel.value;
    prefs.set("show", state.show);
    refresh(true);
  });
  sortSel.addEventListener("change", () => {
    state.sort = sortSel.value;
    state.dir = defaultDir(state.sort);
    prefs.set("sort", state.sort);
    prefs.set("dir", state.dir);
    renderAll(true);
  });
  dirBtn.addEventListener("click", () => {
    state.dir = state.dir === "asc" ? "desc" : "asc";
    prefs.set("dir", state.dir);
    renderAll(true);
  });
  uploadBtn.addEventListener("click", openUpload);
  settingsBtn.addEventListener("click", openSettings);
  const closeMenu = (e) => { if (exportMenu.open && !exportMenu.contains(e.target)) exportMenu.open = false; };
  document.addEventListener("click", closeMenu);
  exportMenu.addEventListener("keydown", (e) => { if (e.key === "Escape") { exportMenu.open = false; exportMenu.querySelector("summary").focus(); } });

  renderAll(true);
  refresh(true).then(() => {
    // Debug/deep-link hooks: #/?dialog=upload | #/?dialog=settings
    const dialog = query.get("dialog");
    if (!alive) return;
    if (dialog === "upload") openUpload();
    else if (dialog === "settings") openSettings();
  });

  return () => {
    alive = false;
    clearTimeout(pollTimer);
    document.removeEventListener("click", closeMenu);
    delete document.body.dataset.view;
  };
}
