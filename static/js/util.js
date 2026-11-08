// DOM + formatting helpers. Every piece of data reaches the page through
// text nodes / attributes set here — never through innerHTML.

const SVG_NS = "http://www.w3.org/2000/svg";

function setStyle(el, style) {
  for (const [prop, val] of Object.entries(style)) {
    if (val == null) continue;
    if (prop.startsWith("--")) el.style.setProperty(prop, String(val));
    else el.style[prop] = val;
  }
}

function applyAttrs(el, attrs) {
  if (!attrs) return;
  for (const [key, val] of Object.entries(attrs)) {
    if (val == null || val === false) continue;
    if (key === "class") {
      const cls = Array.isArray(val) ? val.filter(Boolean).join(" ") : val;
      if (cls) el.setAttribute("class", cls);
    } else if (key === "style" && typeof val === "object") {
      setStyle(el, val);
    } else if (key === "dataset") {
      Object.assign(el.dataset, val);
    } else if (key === "text") {
      el.textContent = String(val);
    } else if (key.startsWith("on") && typeof val === "function") {
      el.addEventListener(key.slice(2).toLowerCase(), val);
    } else if (val === true) {
      el.setAttribute(key, "");
    } else {
      el.setAttribute(key, String(val));
    }
  }
}

function appendChildren(el, children) {
  for (const child of children) {
    if (child == null || child === false || child === true) continue;
    if (Array.isArray(child)) appendChildren(el, child);
    else if (child instanceof Node) el.append(child);
    else el.append(document.createTextNode(String(child)));
  }
}

/** h("div", {class: "x", onClick}, "text", node, [more]) */
export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  applyAttrs(el, attrs);
  appendChildren(el, children);
  return el;
}

/** Same as h() but in the SVG namespace. */
export function s(tag, attrs, ...children) {
  const el = document.createElementNS(SVG_NS, tag);
  applyAttrs(el, attrs);
  appendChildren(el, children);
  return el;
}

export const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

export const prefersReducedMotion = () =>
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const pad2 = (n) => String(n).padStart(2, "0");

/** 43.2 → "0:43" (player clock). */
export function fmtClock(sec) {
  const t = Math.max(0, Math.floor(sec + 1e-6));
  return `${Math.floor(t / 60)}:${pad2(t % 60)}`;
}

/** 64.5 → "01:04.50" (script timecode). */
export function fmtTimecode(sec) {
  const cs = Math.max(0, Math.round(sec * 100));
  const m = Math.floor(cs / 6000);
  const rest = cs - m * 6000;
  return `${pad2(m)}:${pad2(Math.floor(rest / 100))}.${pad2(rest % 100)}`;
}

/** 43.2 → "43s", 75 → "1:15" */
export function fmtLength(sec) {
  if (sec == null || Number.isNaN(sec)) return "—";
  return sec < 60 ? `${Math.round(sec)}s` : fmtClock(sec);
}

export function fmtScore(v, digits = 1) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toFixed(digits);
}

export function plural(n, word, pluralWord = `${word}s`) {
  return `${n} ${n === 1 ? word : pluralWord}`;
}

export function fmtDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/** "threat_or_insult" → "Threat or insult" */
export function humanize(code) {
  if (!code) return "";
  const text = String(code).replace(/_/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

const CLIFFHANGER_TYPES = {
  pre_result: "Pre-result stop",
  twist_line: "Twist line",
  next_event: "Next event",
  emotional_peak: "Emotional peak",
  new_question: "New question",
  other: "Other",
};

export function cliffhangerTypeLabel(code) {
  return CLIFFHANGER_TYPES[code] || humanize(code);
}

export function epLabel(item) {
  if (item.episode_number != null) return `EP ${item.episode_number}`;
  return item.episode_label || "EP ?";
}

let uid = 0;
export const nextId = (prefix = "hl") => `${prefix}-${++uid}`;

/* ---------------------------------------------------------------- icons */

const ICONS = {
  play: [["path", { d: "M8 5.2v13.6a.8.8 0 0 0 1.2.7l10.6-6.8a.8.8 0 0 0 0-1.4L9.2 4.5A.8.8 0 0 0 8 5.2z", fill: "currentColor", stroke: "none" }]],
  pause: [
    ["rect", { x: "6", y: "4.5", width: "4.2", height: "15", rx: "1.2", fill: "currentColor", stroke: "none" }],
    ["rect", { x: "13.8", y: "4.5", width: "4.2", height: "15", rx: "1.2", fill: "currentColor", stroke: "none" }],
  ],
  restart: [["path", { d: "M3.5 12a8.5 8.5 0 1 0 2.6-6.1" }], ["path", { d: "M3.5 4.5v4.5H8" }]],
  upload: [["path", { d: "M12 15.5V4.5" }], ["path", { d: "m7 9 5-5 5 5" }], ["path", { d: "M4.5 19.5h15" }]],
  download: [["path", { d: "M12 4.5v11" }], ["path", { d: "m7 10.5 5 5 5-5" }], ["path", { d: "M4.5 19.5h15" }]],
  settings: [
    ["path", { d: "M4 7h9M17 7h3M4 17h3M11 17h9" }],
    ["circle", { cx: "15", cy: "7", r: "2.2" }],
    ["circle", { cx: "9", cy: "17", r: "2.2" }],
  ],
  trash: [["path", { d: "M4.5 7h15" }], ["path", { d: "M9.5 7V4.5h5V7" }], ["path", { d: "M6.5 7l.9 12.5h9.2L17.5 7" }]],
  back: [["path", { d: "M14.5 18 8.5 12l6-6" }]],
  flip: [["path", { d: "M5 8.5h12.5l-3-3" }], ["path", { d: "M19 15.5H6.5l3 3" }]],
  warn: [["path", { d: "M12 4 2.8 19.5h18.4z" }], ["path", { d: "M12 10v4.2" }], ["path", { d: "M12 17.1v.1" }]],
  error: [["circle", { cx: "12", cy: "12", r: "8.5" }], ["path", { d: "m9.2 9.2 5.6 5.6M14.8 9.2l-5.6 5.6" }]],
  info: [["circle", { cx: "12", cy: "12", r: "8.5" }], ["path", { d: "M12 11v5.5" }], ["path", { d: "M12 7.7v.1" }]],
  check: [["path", { d: "m5 12.5 4.5 4.5L19 7.5" }]],
  close: [["path", { d: "M6.5 6.5l11 11M17.5 6.5l-11 11" }]],
  retry: [["path", { d: "M19.5 12a7.5 7.5 0 1 1-2.2-5.3" }], ["path", { d: "M19.5 4.5v4.5H15" }]],
  copy: [["rect", { x: "8.5", y: "8.5", width: "11", height: "11", rx: "2" }], ["path", { d: "M15.5 8.5V6a1.5 1.5 0 0 0-1.5-1.5H6A1.5 1.5 0 0 0 4.5 6v8A1.5 1.5 0 0 0 6 15.5h2.5" }]],
  file: [["path", { d: "M13.5 3.5H7A1.5 1.5 0 0 0 5.5 5v14A1.5 1.5 0 0 0 7 20.5h10a1.5 1.5 0 0 0 1.5-1.5V8.5z" }], ["path", { d: "M13.5 3.5v5h5" }]],
  camera: [["path", { d: "M3.5 8.5A1.5 1.5 0 0 1 5 7h2.5l1.8-2.2h5.4L16.5 7H19a1.5 1.5 0 0 1 1.5 1.5v9A1.5 1.5 0 0 1 19 19H5a1.5 1.5 0 0 1-1.5-1.5z" }], ["circle", { cx: "12", cy: "12.8", r: "3.3" }]],
  eye: [["path", { d: "M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" }], ["circle", { cx: "12", cy: "12", r: "2.8" }]],
  eyeOff: [["path", { d: "M3.5 3.5l17 17" }], ["path", { d: "M10.2 5.7A9.6 9.6 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a16 16 0 0 1-3 3.8M6.6 6.9A15.6 15.6 0 0 0 2.5 12S6 18.5 12 18.5a9 9 0 0 0 4.6-1.3" }], ["path", { d: "M10 10.1a2.8 2.8 0 0 0 3.9 3.9" }]],
  key: [["circle", { cx: "8", cy: "15.5", r: "3.6" }], ["path", { d: "M10.6 13 19.5 4.1M16.2 7.4l2.6 2.6M13.8 9.8l2 2" }]],
  arrowUp: [["path", { d: "M12 19V5.5M6 11l6-6 6 6" }]],
  arrowDown: [["path", { d: "M12 5v13.5M6 13l6 6 6-6" }]],
  spark: [["path", { d: "M12 3.5l1.9 5.2 5.6.3-4.4 3.5 1.5 5.4L12 14.8l-4.6 3.1 1.5-5.4-4.4-3.5 5.6-.3z" }]],
  scissors: [["circle", { cx: "6.5", cy: "7", r: "2.5" }], ["circle", { cx: "6.5", cy: "17", r: "2.5" }], ["path", { d: "M8.6 8.4 19.5 17.5M8.6 15.6 19.5 6.5" }]],
};

export function icon(name, { size = 18, cls = "", label } = {}) {
  const parts = ICONS[name] || [];
  const el = s("svg", {
    class: ["icon", cls],
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    "stroke-width": "1.9",
    "stroke-linecap": "round",
    "stroke-linejoin": "round",
    "aria-hidden": label ? null : "true",
    role: label ? "img" : null,
    "aria-label": label || null,
    focusable: "false",
  });
  for (const [tag, attrs] of parts) el.append(s(tag, attrs));
  return el;
}

export function spinner(size = 16) {
  return h("span", { class: "spinner", style: { width: `${size}px`, height: `${size}px` }, "aria-hidden": "true" });
}

/** Wordmark used in headers. */
export function wordmark() {
  const mark = s("svg", { class: "wordmark-mark", width: 28, height: 28, viewBox: "0 0 32 32", "aria-hidden": "true" },
    s("defs", null,
      s("linearGradient", { id: "wm-grad", x1: "0", y1: "0", x2: "1", y2: "1" },
        s("stop", { offset: "0", "stop-color": "#ff3d7f" }),
        s("stop", { offset: "1", "stop-color": "#ff8a45" }))),
    s("rect", { width: "32", height: "32", rx: "9", fill: "url(#wm-grad)" }),
    s("path", { d: "M18.5 7v10.5a4.5 4.5 0 1 1-9 0V14.5l3 3", fill: "none", stroke: "#fff", "stroke-width": "2.6", "stroke-linecap": "round", "stroke-linejoin": "round" }),
    s("circle", { cx: "18.5", cy: "7", r: "1.9", fill: "#fff" }));
  return h("a", { class: "wordmark", href: "#/", "aria-label": "Hookline — all promos" },
    mark, h("span", { class: "wordmark-text" }, "Hookline"));
}
