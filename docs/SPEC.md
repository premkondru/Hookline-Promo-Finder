# Hookline — design spec

Hookline reads microdrama screenplays and finds the best 20–60 s promo in each episode.
One promo per episode, 1–3 segments from that episode, ranked across the show.

Stack: Python 3.14 + FastAPI + SQLite (stdlib `sqlite3`) + hand-written HTML/CSS/JS
(ES modules, no build step, no CDNs). Server binds to `127.0.0.1` only.

```
hookline/
  run.py              entry point: python run.py [--port 8765] [--data-dir data] [--fake]
  app/                backend (FastAPI, pipeline, DB)
  static/             frontend (served at /, no build step)
  seed/               bundled episodes, queued on first run (not pre-analyzed)
  data/               runtime DB (gitignored)
  eval/               reference picks + comparison scripts
  tests/              pytest
```

`--fake` swaps Gemini for a deterministic fake provider (no key, no network) so the UI
and tests have realistic data.

---

## 1. Pipeline

1. **Parse** script → numbered blocks `{id, kind: dialogue|action|camera|sfx, speaker, emotion, text, start, end}`.
2. **Pick** (LLM, sees whole episode as numbered blocks): ≤3 candidates. Each: title, 1–3 segments as
   `{start_block, end_block}` in play order, `hook_block`, hook text, `cliffhanger_block`, cliffhanger
   text, open question, one-line why.
3. **Validate** (code): block IDs → exact script timestamps; snap cuts so no dialogue line is clipped;
   enforce 20–60 s total, hook starts ≤3 s into the promo, ≤3 non-overlapping segments. Errors go back
   to the picker for one repair round.
4. **Cold judge** (LLM, sees ONLY the promo transcript with promo-relative times): scores every valid
   candidate on each dimension (1–10, rationale first), lists cold-viewer confusions, picks a tone.
5. **Select** best composite (equal-weight mean). Store winner + all candidates.

## 2. Data model (SQLite)

- `settings(key PK, value)` — `api_key`, `picker_model`, `judge_model`, `seeded`.
- `episodes` — `id`, `content_hash UNIQUE` (SHA-256 of normalized text: BOM stripped, CRLF→LF,
  trailing whitespace trimmed), `show_title`, `episode_number`, `episode_label`, `source_filename`,
  `logline`, `continuity_notes`, `duration_sec`, `raw_text`, `blocks_json`,
  `status (queued|analyzing|done|failed)`, `error`, `created_at`, `updated_at`.
- `promos` — `id`, `episode_id UNIQUE → episodes ON DELETE CASCADE`, title, hook, hook_type,
  cliffhanger, open_question, why, `segments_json`, `duration_sec`, `scores_json`
  (`{dim: {score, rationale}}`), `composite`, `flags_json`, `confusions_json`, `tone`,
  `candidates_json`, `picker_model`, `judge_model`, `prompt_version`, `created_at`.

Deleting a promo deletes its episode (and therefore its hash), so the file can be re-uploaded.

---

## 3. HTTP API (JSON; errors are `{"detail": "..."}` with 4xx/5xx)

Times: `*_sec` are floats in seconds; `start`/`end` strings are script timecodes `MM:SS.ss`.

### `GET /api/config`
```json
{
  "dimensions": [{"key": "hook", "label": "Hook", "question": "Would a scroller stop in the first 3 seconds?"}, "..."],
  "models": [{"id": "gemini-3.8-flash", "label": "Gemini 3.8 Flash", "note": "Default — best balance"}, "..."],
  "limits": {"min_sec": 20, "max_sec": 60, "hook_window_sec": 3, "max_segments": 3},
  "tones": ["betrayal", "romance", "revenge", "danger", "triumph", "mystery", "grief"],
  "fake_mode": false
}
```
Dimension keys (current): `hook, cliffhanger, clarity, stakes, momentum, premise`. **Never hardcode
them in the UI** — the radar has as many vertices as `dimensions` has entries.

### `GET /api/settings` → Settings
```json
{"has_api_key": true, "api_key_hint": "AIza…k2Q", "key_status": "ok|invalid|unverified|missing",
 "key_message": "Key works — 4 of 4 models available", "picker_model": "gemini-3.8-flash",
 "judge_model": "gemini-3.8-flash", "available_models": ["gemini-3.8-flash"] }
```
`available_models` is `null` when unknown. The full key is never returned.

### `PUT /api/settings` body `{"api_key"?: str, "picker_model"?: str, "judge_model"?: str}` → Settings
`api_key: ""` clears the key. Saving a key verifies it against the provider (may take a few seconds).

### `GET /api/shows` → `{"shows": [{"title": "...", "episodes": 50, "promos": 48}]}`

### `GET /api/promos?show=<title>` → `{"promos": [PromoSummary]}`
```json
{
  "id": 3, "episode_id": 3, "rank": 1, "show_title": "I Married a Broken Soldier. He was a Duke",
  "episode_number": 3, "episode_label": "Episode 3", "title": "The Stranger Kneels",
  "hook": "\"Take your hands off her.\"", "hook_type": "shocking_line",
  "cliffhanger": "He kneels with a ring: \"Lady Juliana... accept my hand.\"",
  "open_question": "Will she say yes to a total stranger?", "why": "Public humiliation flips into a rescue and a proposal in under a minute.",
  "duration_sec": 43.2,
  "segments": [{"start_sec": 64.5, "end_sec": 107.7, "start": "01:04.50", "end": "01:47.70", "duration_sec": 43.2}],
  "scores": {"hook": 8, "cliffhanger": 9, "clarity": 7, "stakes": 8, "momentum": 8, "premise": 9},
  "composite": 8.17,
  "flags": [{"level": "warn", "code": "cold_viewer", "message": "Who is the stranger?"}],
  "tone": "romance", "picker_model": "gemini-3.8-flash", "judge_model": "gemini-3.8-flash",
  "created_at": "2026-11-07T21:00:00Z"
}
```
`rank` = position by composite (desc) within the promo's show. `post_first` (bool) marks, per show, the 3
highest-scoring promos that have no blocking flag (`out_of_spec`, `spoiler`, `ad_policy`, `weak_hook`,
`weak_cliffhanger`) and don't repeat a promo already picked, preferring the first third of the series (later
episodes fill in only if too few early ones qualify); the "POST FIRST" ribbon uses it. Summaries also carry `cliffhanger_type` (`pre_result | twist_line |
next_event | emotional_peak | new_question | other`); the detail adds `viewer_question` (the blind judge's
own wording of what the ending leaves open; empty if it couldn't name one). `flags[].level` ∈
`info|warn|error`. Flag codes:

| Level | Codes |
|---|---|
| info | `hook_timing` (on every promo: "Hook lands at 0.4s"), `flash_forward`, `repaired` |
| warn | `tail_after_cliffhanger`, `short_segment`, `dead_air` (> 6 s with no dialogue), `needs_context`, `cold_viewer` (one per judge confusion), `no_open_question`, `spoiler`, `ad_policy` (graphic or sexual content), `duplicate` (repeats another episode's promo: a recap or shared sting), `weak_hook` / `weak_cliffhanger` (that score ≤ 4, which the average can hide) |
| error | `out_of_spec` |

### `GET /api/promos/{id}` → PromoSummary (with `rank`, `post_first` and duplicate flags computed within the promo's show) plus
```json
{
  "rationales": {"hook": "Opens on a stranger's threat mid-scuffle.", "...": "..."},
  "confusions": ["Why is she being dragged out of a church?"],
  "logline": "...", "episode_duration_sec": 145.75, "source_filename": "episode-003-....txt",
  "hook_line_id": 41, "cliffhanger_line_id": 88,
  "lines": [
    {"id": 41, "kind": "dialogue", "speaker": "THE BEARDED STRANGER", "emotion": "Low, Thunderous, Imposing",
     "text": "Take your hands off her.", "src_start": 69.9, "src_end": 72.1, "t_start": 5.4, "t_end": 7.6, "segment": 0}
  ],
  "candidates": [{"label": "A", "title": "...", "selected": true, "valid": true, "composite": 8.17,
                  "scores": {"hook": 8}, "segments": [{"start": "01:04.50", "end": "01:47.70"}], "issues": []}]
}
```
`lines` are all blocks inside the promo, in play order. `t_start`/`t_end` are **promo-relative**
seconds (segment 0 starts at 0; segment 1 starts where segment 0 ended, etc.), already clamped to the
segment. `kind` ∈ `dialogue|action|camera|sfx`; `speaker`/`emotion` are `null` for non-dialogue.

### `DELETE /api/promos/{id}` → `{"deleted": true, "episode_id": 3}` (deletes the episode too)

### `GET /api/episodes` → processing tray (episodes without a finished promo)
```json
{"episodes": [{"id": 51, "show_title": "...", "episode_number": 7, "episode_label": "Episode 7",
               "status": "queued|analyzing|failed", "error": null, "source_filename": "...", "created_at": "..."}],
 "waiting_for_key": true}
```
### `POST /api/episodes/{id}/retry` → `{"ok": true}` · `DELETE /api/episodes/{id}` → `{"deleted": true}`

### `POST /api/upload` (multipart: `files` = one or more `.txt`/`.zip`; optional `show_title`)
```json
{"results": [{"filename": "episode-003.txt", "status": "added|duplicate|invalid", "episode_id": 51,
              "message": "Queued for analysis"}],
 "added": 1, "duplicates": 0, "invalid": 0}
```
Duplicate message names the existing episode, e.g. `Already in the app as Episode 3 of "<show>"`.
If `show_title` is empty: zip → its top folder name; loose `.txt` → `"Untitled show"`.

### `GET /api/export?format=csv|md[&show=]` → file download of the ranked list.

---

## 4. UI

Dark, cinematic, "streaming app" feel. System font stack
(`"Segoe UI Variable", "Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif`).
Hash routes: `#/` list, `#/promo/:id` detail. All user/LLM/script text is inserted with
`textContent` (never `innerHTML` with data). No external network requests from the page.

Tone accents (used for gradients/highlights): betrayal `#e11d48`, romance `#f472b6`, revenge
`#f59e0b`, danger `#f97316`, triumph `#facc15`, mystery `#8b5cf6`, grief `#60a5fa`.

### List page (`#/`)
- Header: "Hookline" wordmark; show filter (hidden when ≤1 show); sort select (Composite default,
  then each dimension from `/api/config`, Episode #, Duration) + asc/desc toggle; Upload button;
  Settings (gear) button.
- Banner when `waiting_for_key` and episodes are queued: "N episodes waiting — add a Gemini key".
- Processing tray when `/api/episodes` is non-empty: compact chips (EP · status); failed chips show
  the error on hover plus Retry and Delete. Poll `/api/episodes` + `/api/promos` every 2 s while any
  episode is queued/analyzing; stop polling when idle.
- Promo rows (cards), in the selected order: position number; EP badge; title; hook as a quote;
  meta line (duration · segment count · `01:04.50 → 01:47.70`); one tiny bar per dimension with its
  score; composite badge; flag icons (tooltip = messages); delete button (confirm dialog:
  "Delete this promo and Episode N? You can re-upload the episode later."). The top 3 by composite
  get a small "POST FIRST" ribbon. Click row → detail.
- Empty state: "No promos yet — upload episodes (.txt or .zip)".

### Upload dialog
Drop zone + file picker (multiple `.txt`/`.zip`), optional show title (datalist of existing shows),
Upload → per-file result list (added ✓ / duplicate ⟳ with message / invalid ✗ with message).

### Settings dialog
API key (password field with show/hide; placeholder shows `api_key_hint` when set; Clear key),
"Save & verify" → shows `key_status` + `key_message`. Picker model and Judge model selects from
`config.models`; options not in `available_models` (when known) are disabled with "(not available
for this key)". Short note: "Picker finds candidate promos; Judge scores them blind."

### Detail page (`#/promo/:id`)
Two columns on a full-page gradient tinted by the promo's `tone` (blank otherwise). Back link top-left.
- **Left: phone cutout** — rounded rectangle, 9:16, about 380 px wide (scales down on small screens),
  no phone chrome. Spotify-lyrics player:
  - Lines in play order. Dialogue = speaker in small caps above bold text; action/sfx = italic,
    dimmer; camera lines hidden unless "Show camera" toggle is on.
  - A clock runs in promo time (requestAnimationFrame). Active line = latest visible line with
    `t_start ≤ now`: bright and full opacity; others dimmed. The list auto-scrolls smoothly to keep
    the active line about a third of the way down.
  - Between segments, a "CUT → 01:47.70" divider.
  - Badges: "HOOK" on `hook_line_id`, "CLIFFHANGER" on `cliffhanger_line_id`.
  - Bottom controls inside the cutout: play/pause, restart, progress bar (click/drag to scrub) with
    the first `hook_window_sec` shaded as the hook zone and ticks at segment boundaries, time
    `0:12 / 0:43`, source timecode of the active line (`EP 3 · 01:16.40`). Clicking a line seeks to it.
  - Autoplay on open; respects `prefers-reduced-motion` (no smooth scroll, instant highlight).
- **Right: score card** — a card that flips (CSS 3D) between two faces via a "Details ⇄" button:
  - Front: the x-agon radar (SVG, one axis per dimension, rings at 2/4/6/8/10, filled polygon in
    the tone color, labels with scores). Hover/focus a vertex → tooltip with that dimension's
    rationale. Composite score shown large.
  - Back (Details): title; segments table (EP · start → end · duration); Hook; Cliffhanger + open
    question; Why it works; Flags and cold-viewer confusions; candidates considered (collapsed list
    with their composites); models used.
- Delete button (same confirm as list).
