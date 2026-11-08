// x-agon radar: one axis per dimension from /api/config, scores 0–10.
// Dataviz specs: single series (no legend box — the card title names it),
// 2px stroke with round joins, ~10% area wash, 10px markers with a 2px surface
// ring, hairline solid rings/spokes one step off the surface, labels in ink
// tokens (never the series color), hit targets >= 28px, hover == focus, and a
// table twin for screen readers.
import { h, s, fmtScore, prefersReducedMotion } from "../util.js";

const W = 460;
const H = 420;
const CX = W / 2;
const CY = H / 2 + 4;
const R = 132;
const RINGS = [2, 4, 6, 8, 10];

const angle = (i, n) => -Math.PI / 2 + (2 * Math.PI * i) / n;
const point = (i, n, r) => [CX + r * Math.cos(angle(i, n)), CY + r * Math.sin(angle(i, n))];
const pts = (list) => list.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");

export function createRadar({ dimensions, scores = {}, rationales = {}, title = "Scores" }) {
  const n = dimensions.length;
  const values = dimensions.map((d) => {
    const v = Number(scores[d.key]);
    return Number.isFinite(v) ? Math.max(0, Math.min(10, v)) : null;
  });

  const svg = s("svg", {
    class: "radar-svg",
    viewBox: `0 0 ${W} ${H}`,
    role: "group",
    "aria-label": `${title}: radar chart of ${n} dimensions scored out of 10`,
  });

  if (n < 3) {
    svg.append(s("text", { x: CX, y: CY, class: "radar-empty", "text-anchor": "middle" }, "Needs at least 3 dimensions"));
    return { el: h("div", { class: "radar" }, svg), destroy() {} };
  }

  // Grid: x-agon rings + spokes (hairlines, solid).
  const grid = s("g", { class: "radar-grid", "aria-hidden": "true" });
  for (const ring of RINGS) {
    const ringPts = dimensions.map((_, i) => point(i, n, (R * ring) / 10));
    grid.append(s("polygon", { class: ring === 10 ? "radar-ring radar-ring-outer" : "radar-ring", points: pts(ringPts) }));
  }
  for (let i = 0; i < n; i++) {
    const [x, y] = point(i, n, R);
    grid.append(s("line", { class: "radar-spoke", x1: CX, y1: CY, x2: x.toFixed(2), y2: y.toFixed(2) }));
  }
  svg.append(grid);

  // Data polygon (grows from the center on first paint).
  const dataPts = values.map((v, i) => point(i, n, (R * (v ?? 0)) / 10));
  const dataGroup = s("g", { class: "radar-data", "aria-hidden": "true", style: { transformOrigin: `${CX}px ${CY}px` } },
    s("polygon", { class: "radar-area", points: pts(dataPts) }),
    s("polygon", { class: "radar-line", points: pts(dataPts) }));
  const markers = dataPts.map(([x, y], i) =>
    s("circle", { class: ["radar-marker", values[i] == null && "is-missing"], cx: x.toFixed(2), cy: y.toFixed(2), r: 5 }));
  dataGroup.append(...markers);
  svg.append(dataGroup);

  // Axis labels: dimension (secondary ink) + score (primary ink).
  const labels = s("g", { class: "radar-labels", "aria-hidden": "true" });
  dimensions.forEach((d, i) => {
    const a = angle(i, n);
    const cos = Math.cos(a);
    const sin = Math.sin(a);
    const [x, y] = point(i, n, R + 20);
    const anchor = cos > 0.3 ? "start" : cos < -0.3 ? "end" : "middle";
    let labelY;
    let scoreY;
    if (sin < -0.5) { labelY = y - 20; scoreY = y - 1; }
    else if (sin > 0.5) { labelY = y + 13; scoreY = y + 33; }
    else { labelY = y - 5; scoreY = y + 15; }
    labels.append(
      s("text", { class: "radar-label", x: x.toFixed(1), y: labelY.toFixed(1), "text-anchor": anchor }, d.label),
      s("text", { class: "radar-score", x: x.toFixed(1), y: scoreY.toFixed(1), "text-anchor": anchor },
        values[i] == null ? "—" : fmtScore(values[i], Number.isInteger(values[i]) ? 0 : 1)));
  });
  svg.append(labels);

  // Hit targets (focusable), drawn last so they sit on top. Low scores would pile
  // the targets up at the center, so they never sit closer than 0.32R.
  const hitPts = values.map((v, i) => point(i, n, Math.max((R * (v ?? 0)) / 10, R * 0.32)));
  const hits = s("g", { class: "radar-hits" });
  hitPts.forEach(([x, y], i) => {
    const d = dimensions[i];
    const why = rationales[d.key] ? ` ${rationales[d.key]}` : "";
    const circle = s("circle", {
      class: "radar-hit",
      cx: x.toFixed(2),
      cy: y.toFixed(2),
      r: 15,
      tabindex: 0,
      role: "img",
      "aria-label": `${d.label}: ${values[i] == null ? "no score" : `${fmtScore(values[i], 0)} out of 10`}.${why}`,
    });
    circle.addEventListener("pointerenter", () => showTip(i));
    circle.addEventListener("pointerleave", hideTip);
    circle.addEventListener("focus", () => showTip(i));
    circle.addEventListener("blur", hideTip);
    hits.append(circle);
  });
  svg.append(hits);

  // Tooltip: value leads, label follows, rationale below.
  const tipValue = h("span", { class: "radar-tip-value" });
  const tipLabel = h("span", { class: "radar-tip-label" });
  const tipQuestion = h("p", { class: "radar-tip-question" });
  const tipWhy = h("p", { class: "radar-tip-why" });
  const tip = h("div", { class: "radar-tip", hidden: true, "aria-hidden": "true" },
    h("div", { class: "radar-tip-head" }, tipValue, h("span", { class: "radar-tip-den" }, "/10"), tipLabel),
    tipQuestion, tipWhy);

  // Table twin (visually hidden).
  const table = h("table", { class: "sr-only" },
    h("caption", null, title),
    h("thead", null, h("tr", null, h("th", { scope: "col" }, "Dimension"), h("th", { scope: "col" }, "Score"), h("th", { scope: "col" }, "Rationale"))),
    h("tbody", null, dimensions.map((d, i) =>
      h("tr", null,
        h("th", { scope: "row" }, d.label),
        h("td", null, values[i] == null ? "—" : `${fmtScore(values[i], 0)}/10`),
        h("td", null, rationales[d.key] || "")))));

  const el = h("div", { class: "radar" }, svg, tip, table);

  function showTip(i) {
    const d = dimensions[i];
    markers.forEach((m, j) => m.classList.toggle("is-hot", j === i));
    tipValue.textContent = values[i] == null ? "—" : fmtScore(values[i], 0);
    tipLabel.textContent = d.label;
    tipQuestion.textContent = d.question || "";
    tipQuestion.hidden = !d.question;
    tipWhy.textContent = rationales[d.key] || "No rationale recorded.";
    tip.hidden = false;
    // Place near the vertex, inside the radar box.
    // The SVG letterboxes inside its box (preserveAspectRatio "meet").
    const box = el.getBoundingClientRect();
    const svgBox = svg.getBoundingClientRect();
    const scale = Math.min(svgBox.width / W, svgBox.height / H);
    const offX = (svgBox.width - W * scale) / 2;
    const offY = (svgBox.height - H * scale) / 2;
    const [vx, vy] = hitPts[i];
    const px = svgBox.left - box.left + offX + vx * scale;
    const py = svgBox.top - box.top + offY + vy * scale;
    const tw = tip.offsetWidth;
    const th = tip.offsetHeight;
    let left = px - tw / 2;
    left = Math.max(4, Math.min(left, box.width - tw - 4));
    let top = py - th - 18;
    if (top < 4) top = py + 18;
    tip.style.left = `${Math.round(left)}px`;
    tip.style.top = `${Math.round(top)}px`;
  }
  function hideTip() {
    tip.hidden = true;
    markers.forEach((m) => m.classList.remove("is-hot"));
  }

  // Entrance animation.
  if (!prefersReducedMotion()) {
    dataGroup.classList.add("is-collapsed");
    requestAnimationFrame(() => requestAnimationFrame(() => dataGroup.classList.remove("is-collapsed")));
  }

  return { el, destroy() { hideTip(); } };
}
