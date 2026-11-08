// App-wide state: the server config (dimensions, models, limits) and tone styling.
import { api } from "./api.js";

let config = null;

export async function loadConfig() {
  config = await api.config();
  return config;
}

export function getConfig() {
  return config;
}

export function dimensions() {
  return (config && config.dimensions) || [];
}

export function limits() {
  return (config && config.limits) || { min_sec: 20, max_sec: 60, hook_window_sec: 3, max_segments: 3 };
}

/*
 * Tones tint each promo.
 * - `accent`: bright decorative colour (page glow, badges, hook zone; SPEC §4);
 *   `ink` is the text colour that reads best on it (white or near-black by contrast).
 * - `mark`: radar polygon/markers — steps from the dataviz reference palette's dark
 *   column, checked with validate_palette.js against the card surface #17141f: all
 *   inside the dark lightness band, chroma >= 0.10, >= 4.6:1. One tone per chart, so
 *   adjacent-pair CVD separation does not apply.
 * - `stage`: the lyrics cutout, a deep saturated shade (≈ Tailwind 800 → 950).
 * - `lyric`: [upcoming, past] line colours = white mixed 52–62% / 80% into stage[0].
 *   Checked with validate_palette.js contrast() at the cutout's lightest point (stage[0]
 *   under the 12% accent glow): upcoming >= 3.3:1, past >= 5:1, active white >= 7:1.
 */
export const TONES = {
  betrayal: { label: "Betrayal", accent: "#e11d48", ink: "#ffffff", mark: "#e66767", stage: ["#8a1730", "#4f0b19"], lyric: ["#c8929e", "#e8d1d6"] },
  romance: { label: "Romance", accent: "#f472b6", ink: "#1a0b12", mark: "#d55181", stage: ["#8a1544", "#4d0c2b"], lyric: ["#cd9aaf", "#e8d0da"] },
  revenge: { label: "Revenge", accent: "#f59e0b", ink: "#1a0b12", mark: "#c98500", stage: ["#7a3311", "#3f1b08"], lyric: ["#c6a799", "#e4d6cf"] },
  danger: { label: "Danger", accent: "#f97316", ink: "#1a0b12", mark: "#d95926", stage: ["#931f0d", "#4f1008"], lyric: ["#d2a199", "#e9d2cf"] },
  triumph: { label: "Triumph", accent: "#facc15", ink: "#1a0b12", mark: "#c98500", stage: ["#6e4304", "#3b2302"], lyric: ["#c8b8a0", "#e2d9cd"] },
  mystery: { label: "Mystery", accent: "#8b5cf6", ink: "#1a0b12", mark: "#9085e9", stage: ["#5221a8", "#2e1263"], lyric: ["#ac94d5", "#dcd3ee"] },
  grief: { label: "Grief", accent: "#60a5fa", ink: "#1a0b12", mark: "#3987e5", stage: ["#1d3c9e", "#12275e"], lyric: ["#97a5d2", "#d2d8ec"] },
};

export const DEFAULT_TONE = { label: "Drama", accent: "#a78bfa", ink: "#1a0b12", mark: "#9085e9", stage: ["#4a2d8f", "#26164f"], lyric: ["#a89ac9", "#dbd5e9"] };

export function tone(name) {
  return TONES[name] || DEFAULT_TONE;
}

export function toneVars(name) {
  const t = tone(name);
  return {
    "--tone": t.accent,
    "--tone-ink": t.ink,
    "--mark": t.mark,
    "--stage-a": t.stage[0],
    "--stage-b": t.stage[1],
    "--lyric-up": t.lyric[0],
    "--lyric-past": t.lyric[1],
  };
}

/** Light persistence for list preferences. */
export const prefs = {
  get(key, fallback) {
    try {
      const v = localStorage.getItem(`hookline.${key}`);
      return v == null ? fallback : v;
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try { localStorage.setItem(`hookline.${key}`, value); } catch { /* storage unavailable */ }
  },
};
