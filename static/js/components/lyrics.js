// Spotify-lyrics-style promo player for the phone cutout.
// The clock runs in promo time (segment 0 starts at 0, segment 1 continues where
// segment 0 ended, …); every line carries promo-relative t_start/t_end from the API.
import { h, icon, clamp, fmtClock, fmtTimecode, prefersReducedMotion, epLabel } from "../util.js";
import { limits } from "../state.js";

const KIND_LABEL = { action: "Action", sfx: "Sound", camera: "Camera" };
const USER_SCROLL_HOLD_MS = 2500;

export function createLyricsPlayer(promo, { autoplay = true, startAt = 0 } = {}) {
  const reduced = prefersReducedMotion();

  // Segment offsets in promo time.
  let acc = 0;
  const segs = (promo.segments || []).map((seg) => {
    const dur = Number(seg.duration_sec ?? (seg.end_sec - seg.start_sec)) || 0;
    const out = { ...seg, dur, offset: acc };
    acc += dur;
    return out;
  });
  const lines = (promo.lines || [])
    .filter((l) => Number.isFinite(Number(l.t_start)))
    .map((l, i) => ({ ...l, t_start: Number(l.t_start), t_end: Number(l.t_end ?? l.t_start), _i: i }))
    .sort((a, b) => a.t_start - b.t_start || a._i - b._i);
  const lastEnd = lines.reduce((m, l) => Math.max(m, l.t_end), 0);
  const total = Math.max(acc || Number(promo.duration_sec) || lastEnd, 0.1);
  const hookWindow = Math.min(Number(limits().hook_window_sec ?? 3), total);
  const pct = (t) => `${(clamp(t / total, 0, 1) * 100).toFixed(3)}%`;

  /* ------------------------------------------------------------ lyric list */
  const list = h("ol", { class: "lyrics-list" });
  const items = [];
  const cuts = [];
  let prevSeg = null;
  for (const line of lines) {
    if (prevSeg !== null && line.segment !== prevSeg) {
      const seg = segs[line.segment];
      const cut = h("li", { class: "lyrics-cut" },
        h("span", { class: "lyrics-cut-rule", "aria-hidden": "true" }),
        h("span", { class: "lyrics-cut-label" }, icon("scissors", { size: 13 }), `CUT → ${seg ? seg.start : fmtTimecode(line.src_start ?? 0)}`),
        h("span", { class: "lyrics-cut-rule", "aria-hidden": "true" }));
      cuts.push({ el: cut, at: seg ? seg.offset : line.t_start });
      list.append(cut);
    }
    prevSeg = line.segment;

    const isHook = promo.hook_line_id != null && line.id === promo.hook_line_id;
    const isCliff = promo.cliffhanger_line_id != null && line.id === promo.cliffhanger_line_id;
    const label = line.kind === "dialogue"
      ? [h("span", { class: "lyric-speaker-name" }, line.speaker || "Unknown"),
        line.emotion ? h("span", { class: "lyric-emotion" }, line.emotion) : null]
      : h("span", { class: "lyric-speaker-name" }, KIND_LABEL[line.kind] || line.kind || "");
    const el = h("li", { class: ["lyric", `lyric-${line.kind}`] },
      h("div", { class: "lyric-meta" },
        isHook ? h("span", { class: "lyric-badge badge-hook" }, "Hook") : null,
        isCliff ? h("span", { class: "lyric-badge badge-cliff" }, "Cliffhanger") : null,
        h("span", { class: "lyric-speaker" }, label)),
      h("p", { class: "lyric-text" }, line.text || ""));
    el.addEventListener("click", () => seek(line.t_start, { scroll: true }));
    // Lines carrying a badge stay visible even when camera lines are hidden.
    items.push({ line, el, pinned: isHook || isCliff });
    list.append(el);
  }
  if (!items.length) {
    list.append(h("li", { class: "lyric lyric-empty" }, h("p", { class: "lyric-text" }, "No script lines in this promo.")));
  }

  const viewport = h("div", { class: "lyrics-viewport" }, list);

  /* ------------------------------------------------------------ controls */
  const fill = h("div", { class: "progress-fill" });
  const thumb = h("div", { class: "progress-thumb" });
  const ticks = segs.slice(1).map((seg) => h("i", { class: "progress-tick", style: { left: pct(seg.offset) } }));
  const progress = h("div", {
    class: "progress",
    role: "slider",
    tabindex: 0,
    "aria-label": "Playback position",
    "aria-valuemin": "0",
    "aria-valuemax": total.toFixed(1),
  },
  h("div", { class: "progress-track" },
    h("div", { class: "progress-hook", style: { width: pct(hookWindow) }, "data-tip": `Hook window — first ${hookWindow} s` }),
    fill,
    ticks),
  thumb);

  const elapsedEl = h("span", { class: "player-time" }, "0:00");
  const srcEl = h("span", { class: "player-src", "data-tip": "Timecode in the episode" }, "");
  const totalEl = h("span", { class: "player-time" }, fmtClock(total));
  const segEl = h("span", { class: "player-seg" }, "");

  const playIcon = icon("play", { size: 26 });
  const pauseIcon = icon("pause", { size: 26 });
  const playBtn = h("button", { class: "player-play", type: "button", "aria-label": "Play" }, playIcon);
  const restartBtn = h("button", { class: "player-btn", type: "button", "aria-label": "Restart", "data-tip": "Restart" }, icon("restart", { size: 19 }));
  const camBtn = h("button", {
    class: "player-btn",
    type: "button",
    "aria-pressed": "false",
    "aria-label": "Show camera directions",
    "data-tip": "Show camera directions",
  }, icon("camera", { size: 19 }));

  const el = h("div", { class: "phone" },
    h("div", { class: "phone-top" },
      h("span", { class: "phone-ep" }, epLabel(promo)),
      h("span", { class: "phone-title" }, promo.title || "Untitled promo")),
    viewport,
    h("div", { class: "phone-controls" },
      progress,
      h("div", { class: "player-times" }, elapsedEl, srcEl, totalEl),
      h("div", { class: "player-buttons" },
        h("div", { class: "player-side" }, camBtn),
        h("div", { class: "player-center" }, restartBtn, playBtn, h("span", { class: "player-btn-spacer", "aria-hidden": "true" })),
        h("div", { class: "player-side player-side-end" }, segEl))));

  /* ------------------------------------------------------------ state */
  let showCamera = false;
  let visible = [];
  let activeIdx = -2; // forces first paint
  let now = clamp(Number(startAt) || 0, 0, total);
  let playing = false;
  let base = now;
  let t0 = 0;
  let raf = 0;
  let userScrollUntil = 0;
  let lastAria = -1;

  function computeVisible() {
    visible = items.filter((it) => showCamera || it.line.kind !== "camera" || it.pinned);
    list.classList.toggle("show-camera", showCamera);
    for (const it of items) it.el.hidden = !(showCamera || it.line.kind !== "camera" || it.pinned);
  }

  function findActive(t) {
    let idx = -1;
    for (let i = 0; i < visible.length; i++) {
      if (visible[i].line.t_start <= t + 0.02) idx = i;
      else break;
    }
    return idx;
  }

  function scrollToActive(instant) {
    if (performance.now() < userScrollUntil) return;
    const target = activeIdx >= 0 ? visible[activeIdx].el : null;
    const top = target ? target.offsetTop - viewport.clientHeight * 0.32 : 0;
    viewport.scrollTo({ top: Math.max(0, top), behavior: instant || reduced ? "auto" : "smooth" });
  }

  function paintLines(force = false, instant = false) {
    const idx = findActive(now);
    if (idx === activeIdx && !force) return;
    activeIdx = idx;
    visible.forEach((it, i) => {
      it.el.classList.toggle("is-active", i === idx);
      it.el.classList.toggle("is-past", i < idx);
    });
    for (const cut of cuts) cut.el.classList.toggle("is-past", now >= cut.at - 0.02);
    scrollToActive(instant);
  }

  function segmentAt(t) {
    for (let i = segs.length - 1; i >= 0; i--) if (t >= segs[i].offset - 1e-6) return i;
    return 0;
  }

  let lastElapsed = "";
  let lastSrc = "";
  function paintControls() {
    const p = pct(now);
    fill.style.width = p;
    thumb.style.left = p;
    const elapsed = fmtClock(now);
    if (elapsed !== lastElapsed) { elapsedEl.textContent = elapsed; lastElapsed = elapsed; }
    if (segs.length) {
      const i = segmentAt(now);
      const seg = segs[i];
      const src = `${epLabel(promo)} · ${fmtTimecode(Number(seg.start_sec) + clamp(now - seg.offset, 0, seg.dur))}`;
      if (src !== lastSrc) { srcEl.textContent = src; lastSrc = src; }
      segEl.textContent = segs.length > 1 ? `Segment ${i + 1}/${segs.length}` : "1 segment";
    }
    const whole = Math.floor(now);
    if (whole !== lastAria) {
      lastAria = whole;
      progress.setAttribute("aria-valuenow", now.toFixed(1));
      progress.setAttribute("aria-valuetext", `${fmtClock(now)} of ${fmtClock(total)}`);
    }
  }

  function paint(force = false, instant = false) {
    paintControls();
    paintLines(force, instant);
  }

  function setPlayingUi() {
    playBtn.replaceChildren(playing ? pauseIcon : playIcon);
    playBtn.setAttribute("aria-label", playing ? "Pause" : "Play");
    el.classList.toggle("is-playing", playing);
  }

  function frame() {
    now = base + (performance.now() - t0) / 1000;
    if (now >= total) {
      now = total;
      playing = false;
      base = now;
      setPlayingUi();
      paint();
      el.classList.add("is-ended");
      return;
    }
    paint();
    raf = requestAnimationFrame(frame);
  }

  function play() {
    if (playing) return;
    if (now >= total - 0.05) seek(0, { scroll: true });
    el.classList.remove("is-ended");
    base = now;
    t0 = performance.now();
    playing = true;
    setPlayingUi();
    raf = requestAnimationFrame(frame);
  }

  function pause() {
    if (!playing) return;
    cancelAnimationFrame(raf);
    now = base + (performance.now() - t0) / 1000;
    now = clamp(now, 0, total);
    base = now;
    playing = false;
    setPlayingUi();
    paint();
  }

  function toggle() { if (playing) pause(); else play(); }

  function seek(t, { scroll = false, instant = false } = {}) {
    now = clamp(t, 0, total);
    base = now;
    t0 = performance.now();
    if (now < total) el.classList.remove("is-ended");
    if (scroll) userScrollUntil = 0;
    paint(scroll, instant);
  }

  /* ------------------------------------------------------------ events */
  playBtn.addEventListener("click", toggle);
  restartBtn.addEventListener("click", () => { seek(0, { scroll: true }); play(); });
  camBtn.addEventListener("click", () => {
    showCamera = !showCamera;
    camBtn.setAttribute("aria-pressed", String(showCamera));
    camBtn.classList.toggle("is-on", showCamera);
    const label = showCamera ? "Hide camera directions" : "Show camera directions";
    camBtn.setAttribute("aria-label", label);
    camBtn.setAttribute("data-tip", label);
    computeVisible();
    userScrollUntil = 0;
    paintLines(true, true);
  });

  const holdScroll = () => { userScrollUntil = performance.now() + USER_SCROLL_HOLD_MS; };
  viewport.addEventListener("wheel", holdScroll, { passive: true });
  viewport.addEventListener("touchstart", holdScroll, { passive: true });

  let wasPlaying = false;
  let dragging = false;
  const timeFromPointer = (e) => {
    const r = progress.getBoundingClientRect();
    return clamp((e.clientX - r.left) / r.width, 0, 1) * total;
  };
  progress.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    dragging = true;
    wasPlaying = playing;
    pause();
    progress.setPointerCapture(e.pointerId);
    progress.classList.add("is-dragging");
    seek(timeFromPointer(e), { scroll: true, instant: true });
  });
  progress.addEventListener("pointermove", (e) => {
    if (dragging) seek(timeFromPointer(e), { scroll: true, instant: true });
  });
  const endDrag = (e) => {
    if (!dragging) return;
    dragging = false;
    progress.classList.remove("is-dragging");
    if (progress.hasPointerCapture(e.pointerId)) progress.releasePointerCapture(e.pointerId);
    if (wasPlaying) play();
  };
  progress.addEventListener("pointerup", endDrag);
  progress.addEventListener("pointercancel", endDrag);
  progress.addEventListener("keydown", (e) => {
    const step = e.shiftKey ? 5 : 1;
    const map = {
      ArrowLeft: now - step, ArrowDown: now - step, ArrowRight: now + step, ArrowUp: now + step,
      PageDown: now - 10, PageUp: now + 10, Home: 0, End: total,
    };
    if (e.key in map) {
      e.preventDefault();
      seek(map[e.key], { scroll: true });
    }
  });

  const onVisibility = () => { if (document.hidden) pause(); };
  document.addEventListener("visibilitychange", onVisibility);

  /* ------------------------------------------------------------ start */
  computeVisible();
  paint(true, true);
  let autoTimer = 0;
  if (autoplay) autoTimer = setTimeout(play, 650);

  return {
    el,
    play,
    pause,
    toggle,
    seek: (t) => seek(t, { scroll: true }),
    get playing() { return playing; },
    get time() { return now; },
    get duration() { return total; },
    relayout() { paintLines(true, true); },
    destroy() {
      clearTimeout(autoTimer);
      cancelAnimationFrame(raf);
      playing = false;
      document.removeEventListener("visibilitychange", onVisibility);
    },
  };
}
