// Detail page: phone-cutout lyrics player (left) + flip card with the x-agon
// radar on the front and the promo details on the back (right).
import { h, icon, spinner, fmtScore, fmtLength, fmtDateTime, epLabel, plural, prefersReducedMotion, humanize, cliffhangerTypeLabel } from "../util.js";
import { api } from "../api.js";
import { dimensions, tone, toneVars } from "../state.js";
import { createRadar } from "../components/radar.js";
import { createLyricsPlayer } from "../components/lyrics.js";
import { confirmDialog } from "../components/dialog.js";
import { toast, toastError } from "../components/toast.js";
import { navigate } from "../router.js";

const FLAG_ICON = { error: "error", warn: "warn", info: "info" };

function section(title, ...content) {
  return h("section", { class: "detail-section" }, h("h3", { class: "detail-h" }, title), ...content);
}

function segmentsTable(p) {
  const segs = p.segments || [];
  return h("table", { class: "data-table" },
    h("thead", null, h("tr", null,
      h("th", { scope: "col" }, "#"),
      h("th", { scope: "col" }, "Episode"),
      h("th", { scope: "col" }, "Start → End"),
      h("th", { scope: "col", class: "num" }, "Length"))),
    h("tbody", null, segs.map((seg, i) => h("tr", null,
      h("td", { class: "num" }, String(i + 1)),
      h("td", null, p.episode_label || epLabel(p)),
      h("td", { class: "mono" }, `${seg.start} → ${seg.end}`),
      h("td", { class: "num" }, fmtLength(seg.duration_sec ?? (seg.end_sec - seg.start_sec)))))),
    segs.length > 1
      ? h("tfoot", null, h("tr", null, h("td", { colspan: 3 }, "Total"), h("td", { class: "num" }, fmtLength(p.duration_sec))))
      : null);
}

function scoresTable(p) {
  return h("table", { class: "data-table data-table-scores" },
    h("thead", null, h("tr", null,
      h("th", { scope: "col" }, "Dimension"),
      h("th", { scope: "col", class: "num" }, "Score"),
      h("th", { scope: "col" }, "Why"))),
    h("tbody", null, dimensions().map((d) => h("tr", null,
      h("th", { scope: "row" }, d.label),
      h("td", { class: "num strong" }, fmtScore(p.scores?.[d.key], 0)),
      h("td", { class: "muted" }, (p.rationales && p.rationales[d.key]) || "—")))));
}

// Problems (warn/error) first; cold_viewer flags are shown through the confusions
// list instead of twice; info flags are quiet notes. hook_timing lives in the Hook
// section.
function qualityList(p) {
  const flags = p.flags || [];
  const confusions = p.confusions || [];
  const problems = flags.filter((f) => (f.level === "error" || f.level === "warn") && !(f.code === "cold_viewer" && confusions.length));
  const notes = flags.filter((f) => f.level === "info" && f.code !== "hook_timing");
  if (!problems.length && !confusions.length && !notes.length) {
    return h("p", { class: "muted" }, "No quality flags — this pick passed every check.");
  }
  return h("div", { class: "quality" },
    problems.length
      ? h("ul", { class: "flag-list" }, problems.map((f) =>
        h("li", { class: ["flag-item", `flag-${f.level}`] },
          icon(FLAG_ICON[f.level] || "info", { size: 15 }),
          h("span", null, f.message),
          f.code ? h("span", { class: "flag-code" }, f.code.replace(/_/g, " ")) : null)))
      : h("p", { class: "muted" }, "No warnings."),
    confusions.length
      ? h("div", { class: "confusions" },
        h("p", { class: "confusions-title" }, "A first-time viewer might ask"),
        h("ul", null, confusions.map((c) => h("li", null, c))))
      : null,
    notes.length
      ? h("ul", { class: "notes-list" }, notes.map((f) => h("li", null, icon("info", { size: 13 }), h("span", null, f.message))))
      : null);
}

function hookNote(p) {
  const f = (p.flags || []).find((x) => x.code === "hook_timing");
  return f ? h("span", { class: "hook-note" }, f.message) : null;
}

function candidatesList(p) {
  const cands = p.candidates || [];
  if (!cands.length) return null;
  return h("details", { class: "candidates" },
    h("summary", null, `Candidates considered (${cands.length})`),
    h("ul", { class: "cand-list" }, cands.map((c) =>
      h("li", { class: ["cand", c.selected && "is-selected", c.valid === false && "is-invalid"] },
        h("div", { class: "cand-head" },
          h("span", { class: "cand-label", "data-tip": c.label ? `Candidate ${c.label}` : "Never reached the judge" }, c.label || "–"),
          h("span", { class: "cand-title" }, c.title || "Untitled"),
          c.selected ? h("span", { class: "pill pill-ok" }, "Selected") : null,
          c.valid === false ? h("span", { class: "pill pill-bad" }, "Invalid") : null,
          h("span", { class: "cand-score" }, c.composite == null ? "—" : fmtScore(c.composite))),
        (c.segments || []).length
          ? h("p", { class: "cand-segs mono muted" }, c.segments.map((sg) => `${sg.start} → ${sg.end}`).join("  +  "))
          : null,
        (c.issues || []).length ? h("p", { class: "cand-issues" }, c.issues.join(" · ")) : null))));
}

export function mountDetail(outlet, [id], query) {
  let alive = true;
  let player = null;
  let radar = null;
  let toneKeys = [];

  const page = h("div", { class: "page page-detail" });
  outlet.append(page);
  document.body.dataset.view = "detail";
  page.append(h("div", { class: "detail-loading" }, spinner(24), h("p", null, "Loading promo…")));

  function setTone(name) {
    const vars = toneVars(name);
    toneKeys = Object.keys(vars);
    for (const [k, v] of Object.entries(vars)) document.body.style.setProperty(k, v);
  }

  function renderNotFound(err) {
    page.replaceChildren(
      h("div", { class: "detail-top" }, h("a", { class: "back-link", href: "#/" }, icon("back", { size: 18 }), "All promos")),
      h("div", { class: "empty" },
        h("div", { class: "empty-art is-bad", "aria-hidden": "true" }, icon("error", { size: 30 })),
        h("h2", { class: "empty-title" }, err && err.status === 404 ? "Promo not found" : "Couldn't load this promo"),
        h("p", { class: "muted" }, err && err.status === 404 ? "It may have been deleted along with its episode." : (err && err.message) || ""),
        h("a", { class: "btn btn-primary", href: "#/" }, "Back to all promos")));
  }

  function render(p) {
    setTone(p.tone);
    const t = tone(p.tone);
    const dims = dimensions();

    const delBtn = h("button", { class: "btn btn-glass btn-sm", type: "button" }, icon("trash", { size: 15 }), "Delete");
    delBtn.addEventListener("click", async () => {
      const ok = await confirmDialog({
        title: "Delete promo?",
        message: `Delete this promo and ${p.episode_label || epLabel(p)}? You can re-upload the episode later.`,
      });
      if (!ok) return;
      try {
        await api.deletePromo(p.id);
        toast(`${p.episode_label || epLabel(p)} deleted`, { kind: "success" });
        navigate("/");
      } catch (err) { toastError(err, "Delete failed"); }
    });

    // Left: phone cutout player.
    const startAt = Number(query.get("t")) || 0;
    const paused = query.has("paused");
    player = createLyricsPlayer(p, { autoplay: !paused, startAt });

    // Right: flip card.
    radar = createRadar({ dimensions: dims, scores: p.scores || {}, rationales: p.rationales || {}, title: `${p.title || "Promo"} — scores` });
    const toDetails = h("button", { class: "btn btn-glass btn-sm flip-btn", type: "button", "aria-label": "Show details" }, "Details", icon("flip", { size: 16 }));
    const toRadar = h("button", { class: "btn btn-glass btn-sm flip-btn", type: "button", "aria-label": "Show score radar" }, "Radar", icon("flip", { size: 16 }));

    const head = (btn) => h("div", { class: "card-head" },
      h("span", { class: "ep-badge" }, epLabel(p)),
      h("span", { class: "tone-chip" }, h("i", { class: "tone-dot", "aria-hidden": "true" }), t.label),
      h("span", { class: "card-head-spacer" }),
      btn);

    const front = h("section", { class: "face face-front", "aria-label": "Score radar" },
      head(toDetails),
      h("h1", { class: "card-title" }, p.title || "Untitled promo"),
      p.show_title ? h("p", { class: "card-sub muted" }, p.show_title) : null,
      h("div", { class: "radar-holder" }, radar.el),
      h("div", { class: "hero" },
        h("div", { class: "hero-figure" },
          h("span", { class: "hero-num" }, fmtScore(p.composite)),
          h("span", { class: "hero-den" }, "/10")),
        h("div", { class: "hero-text" },
          h("span", { class: "hero-label" }, "Composite score"),
          h("span", { class: "hero-note muted" }, `Equal-weight average of ${plural(dims.length, "dimension")}`),
          p.rank != null ? h("span", { class: "hero-note muted" }, `#${p.rank} in the ranking`) : null),
        p.post_first
          ? h("span", { class: "ribbon hero-ribbon", "data-tip": "Top-scoring promos from the first third of the series with no spoiler, ad-policy or spec flags" }, icon("spark", { size: 12 }), "Post first")
          : null));

    const back = h("section", { class: "face face-back", "aria-label": "Promo details", inert: true },
      head(toRadar),
      h("div", { class: "details-scroll" },
        h("h2", { class: "card-title card-title-sm" }, p.title || "Untitled promo"),
        section("Segments", segmentsTable(p)),
        section("Hook",
          h("p", { class: "detail-quote" }, p.hook || "—"),
          p.hook_type ? h("span", { class: "tag" }, humanize(p.hook_type)) : null,
          hookNote(p)),
        section("Cliffhanger",
          h("p", { class: "detail-quote" }, p.cliffhanger || "—"),
          p.cliffhanger_type ? h("span", { class: "tag" }, cliffhangerTypeLabel(p.cliffhanger_type)) : null,
          p.open_question
            ? h("p", { class: "detail-question" }, h("span", { class: "muted" }, "Picker's intended question: "), p.open_question)
            : null,
          // The blind judge's own reading of what the ending leaves open.
          p.viewer_question
            ? h("p", { class: "detail-question" }, h("span", { class: "muted" }, "What a cold viewer wants to know: "), p.viewer_question)
            : h("p", { class: "detail-question muted" }, "A cold viewer couldn't name one.")),
        section("Why it works", h("p", null, p.why || "—")),
        section("Scores", scoresTable(p)),
        section("Quality check", qualityList(p)),
        candidatesList(p),
        section("About this pick",
          h("dl", { class: "meta-list" },
            h("dt", null, "Picker"), h("dd", null, p.picker_model || "—"),
            h("dt", null, "Judge"), h("dd", null, p.judge_model || "—"),
            h("dt", null, "Source"), h("dd", { class: "mono" }, p.source_filename || "—"),
            h("dt", null, "Episode length"), h("dd", null, fmtLength(p.episode_duration_sec)),
            h("dt", null, "Analyzed"), h("dd", null, fmtDateTime(p.created_at))),
          p.logline ? h("p", { class: "logline muted" }, h("strong", null, "Episode logline: "), p.logline) : null)));

    const flip = h("div", { class: "flip" }, h("div", { class: "flip-inner" }, front, back));
    function setFace(details, { focus = true } = {}) {
      flip.classList.toggle("is-flipped", details);
      front.inert = details;
      back.inert = !details;
      if (focus) (details ? toRadar : toDetails).focus({ preventScroll: true });
    }
    toDetails.addEventListener("click", () => setFace(true));
    toRadar.addEventListener("click", () => setFace(false));
    if (prefersReducedMotion()) flip.classList.add("no-motion");

    page.replaceChildren(
      h("div", { class: "detail-top" },
        h("a", { class: "back-link", href: "#/" }, icon("back", { size: 18 }), "All promos"),
        h("span", { class: "detail-top-spacer" }),
        delBtn),
      h("div", { class: "detail-grid" },
        h("div", { class: "detail-left" }, player.el),
        h("div", { class: "detail-right" }, flip)));

    if (query.get("face") === "details") setFace(true, { focus: false });
    player.relayout();
  }

  function onKey(e) {
    if (!player || e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey) return;
    if (document.querySelector("dialog[open]")) return;
    const target = e.target instanceof Element ? e.target : null;
    if (target && target.closest("input, textarea, select, button, a, summary, [role=slider], [contenteditable]")) return;
    if (e.key === " ") { e.preventDefault(); player.toggle(); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); player.seek(player.time - 2); }
    else if (e.key === "ArrowRight") { e.preventDefault(); player.seek(player.time + 2); }
  }
  document.addEventListener("keydown", onKey);

  api.promo(id)
    .then((p) => { if (alive) render(p); })
    .catch((err) => { if (alive) renderNotFound(err); });

  return () => {
    alive = false;
    document.removeEventListener("keydown", onKey);
    if (player) player.destroy();
    if (radar) radar.destroy();
    for (const k of toneKeys) document.body.style.removeProperty(k);
    delete document.body.dataset.view;
  };
}
