# Hookline

Hookline reads microdrama screenplays and finds the best 20–60 second promo in each episode. Each promo comes with segment timestamps, the hook, the cliffhanger and a one-line reason it works. Promos are scored on six dimensions and ranked across the show.

It replaces the editor's first pass of watching every episode to shortlist promo moments. The editor still makes the final cut.

## Quick start

Needs Python 3.11+ (built and tested on 3.14). No Node and no build step.

```powershell
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python run.py                   # opens http://127.0.0.1:8765
```

The bundled show, *I Married a Broken Soldier. He was a Duke* (50 episodes), loads on first start with every episode queued. Nothing is pre-analyzed:
1. Open **Settings**, paste a Gemini API key and pick the models.
2. The tool analyzes the queue while you watch.
3. Promos appear in the ranked list as each episode finishes, typically in about 10 minutes for all 50.

To try the interface without a key, run `python run.py --fake`, which uses a simulated LLM with fake scores.

| Option | Effect |
|---|---|
| `--port 8765` | port; the server always binds to 127.0.0.1 |
| `--data-dir data` | where `hookline.db` lives; a fresh folder starts from the bundled seed again |
| `--fake` | simulated LLM, so you can try the app with no key and no network (the scores are fake); uses `data-fake/` unless `--data-dir` is given |
| `--no-browser` | don't open a browser tab |

## Using it

- **Ranked list:** sorted by composite score by default. You can re-sort by any dimension, episode or duration, and filter by show.
- **Post first:** three promos per show are marked *Post first*:
  - They are the highest-scoring promos with no spoiler, ad-policy, out-of-spec, weak-hook or weak-cliffhanger flag.
  - None of them repeats another pick.
  - The first third of the series is preferred: new viewers start at episode 1, so an early-episode promo promises what they get soon after installing, while late-series payoffs spoil the story.
- **Upload:**
  - Accepts `.txt` screenplays or a `.zip` of them. A zip's folder name becomes the show title.
  - Files are de-duplicated by content: re-uploading an episode the app already has is reported as a duplicate, even if it was re-saved with different line endings.
  - New episodes queue for analysis. Progress and failures show in the tray, where you can retry or remove them.
- **Delete:** deleting a promo also deletes its episode, so that file can be uploaded again later.
- **Detail page:**
  - Left: the promo plays as a Spotify-lyrics-style transcript inside a phone-sized frame, timed to the script, with CUT markers and HOOK / CLIFFHANGER badges.
  - Right: the score radar. Hover a vertex to see the judge's reason. **Details** flips the card to show segments, hook, cliffhanger, quality flags and the other candidates considered.
- **Export:** CSV or Markdown of the ranked list.

## How it picks

```
screenplay ─► parse into timed blocks ─► PICKER (Gemini, reads the whole episode)
          ─► up to 3 candidate promos, given as block ranges (never timestamps)
          ─► VALIDATOR (code): block ids → the script's own timecodes, cuts snapped so no line is clipped,
             20–60 s total, hook inside the first 3 s, ≤3 non-overlapping segments; violations go back
             to the picker for one repair round
          ─► JUDGE (Gemini, sees only each clip's transcript, like a first-time viewer)
             scores every candidate 1–10 per dimension with a reason, and lists what a newcomer wouldn't get
          ─► keep the candidate with the best composite
```

Design choices worth knowing:

- **The model never writes timestamps.** It names script blocks, and the code converts them to exact timecodes. Timestamps can't be hallucinated, and every cut lands on a clean line boundary.
- **The judge is blind.** It never sees the episode, its logline or earlier episodes, so "makes sense on its own" is tested against a real cold read instead of an assumption.
- **One promo per episode**, with 1–3 segments from that episode. Cross-episode montages are out of scope.
- **Failures are visible, not hidden.** Flags on each promo show:
  - validator warnings and out-of-spec cuts
  - the judge's cold-viewer confusions
  - the picker's spoiler and ad-policy risks
  - must-haves the average hides: a hook or cliffhanger scored 4 or below
  - promos that repeat another episode's promo.

### Scores

Each dimension is scored 1–10 against anchored descriptions (see `app/config.py`). The composite is their equal-weight mean, and the weights live in the same file.

| Dimension | Question |
|---|---|
| Hook | Would a scroller stop in the first 3 seconds? |
| Cliffhanger | Does the last beat leave a question you need answered? |
| Clarity | Can a first-time viewer follow who's who and what's at stake? |
| Stakes | How intense is the conflict or emotion? |
| Momentum | Does it escalate with no dead air? |
| Premise pull | Does it sell the series' core fantasy, not just one scene? |

### Models

The Settings menu lists Gemini 3.8 Flash (default), Gemini 4 Argon (paid tier only), Gemini 3.6 Flash and Gemini 3.5 Flash-Lite. Each is checked against the models your key can actually use. The picker and judge models can differ.

On the free tier, Google may use submitted content to improve its products, so use a paid-tier key for unreleased scripts.

## Data

SQLite at `data/hookline.db`. Layout:

- `episodes`: each episode's SHA-256 over its normalized text (BOM, CRLF and trailing spaces ignored). This hash is the de-dup key.
- `promos`: one per episode, deleted along with it.
- `settings`: the API key and model choices. The key stays on this machine and is only ever shown masked.

`seed/episodes/` holds the bundled episodes, which are imported (queued, not analyzed) on first start. To snapshot a finished run for the evaluation scripts, writing `eval/run_promos.json`:

```powershell
python -m app.seed export
```

## Results and quality check

**[eval/README.md](eval/README.md)** covers:
- the ranked promos
- what to post first, and why
- where the tool picks badly, with evidence.

Supporting files:
- `eval/ranked_promos.md` / `.csv`: all 50 promos with segments, hook, cliffhanger and why.
- `eval/reference_picks_*.json`: an independent editor pass over all 50 scripts, with the same brief and validated timestamps.
- `eval/run_promos.json`: the snapshot of the analysis run the write-up is based on. It is not loaded into the app.
- `eval/comparison.md`: the tool vs that reference. Regenerate it with `python eval/compare.py --snapshot`.
- `eval/blind_ab/`: blind A/B judgments on the episodes where the two disagreed most.

## Development

```powershell
pip install -r requirements-dev.txt
python -m pytest -q
```

Tests cover parsing all 50 scripts, hashing, timestamp snapping and rule checks, the pipeline (repair round, selection, flags) with a scripted fake LLM, and the API: upload → dedup → analyze → delete → re-upload, settings, export and the security guards.

Security:
- The server listens on 127.0.0.1 only.
- It refuses foreign `Host` headers (DNS rebinding) and cross-origin writes.
- It serves a strict Content-Security-Policy.
- All script and LLM text is inserted into the page as text, never HTML.

```
app/            FastAPI backend: screenplay parser, timeline/validator, prompts, pipeline, worker, API
app/llm/        Gemini provider (google-genai 3.x) and the deterministic fake
static/         frontend: plain HTML/CSS/JS modules
seed/           bundled episodes (queued on first start, not pre-analyzed)
eval/           reference picks + comparison script
docs/SPEC.md    design spec and API contract
tests/          pytest suite
```
