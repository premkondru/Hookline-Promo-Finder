"""Prompts and JSON schemas for the two LLM stages: the picker and the blind judge."""

from __future__ import annotations

from . import config
from .screenplay import Block
from .timeline import fmt_tc

CANDIDATE_LABELS = ["A", "B", "C", "D", "E"]
RISK_TYPES = ["spoiler", "graphic_violence", "sexual_content"]

PICKER_SYSTEM = """\
You are the senior promo editor at a vertical-microdrama studio (ReelShort / DramaBox style). Every week you \
cut 20-60 second promos straight from new episodes. They run on TikTok, Instagram Reels and YouTube Shorts to \
pull in people who have never seen the show, so each promo must work on a cold, scrolling viewer - often with \
the sound off.

A great promo:
1. HOOK - something in the first 3 seconds stops the thumb: a public humiliation, a slap or blow, a threat or \
insult, a betrayal discovered, a stunning reveal. Never an establishing shot, travel or calm setup.
2. CLIFFHANGER - it cuts at an unresolved moment: right before an answer, a blow or a reveal lands, right after \
a line that flips everything, or on the threshold of an arrival. The last line is complete; the suspense comes \
from the unresolved event, not a cut-off sentence. Never end on the payoff or a calm aftermath.
3. STANDALONE - within seconds a stranger knows who is wronged, by whom, and what's at stake.

Use one continuous stretch when it holds both a strong hook and a strong cliffhanger within 60 seconds. When \
the best hook and the best cliffhanger are too far apart, join up to 3 moments from the same episode (e.g. open \
on the most shocking line, then jump to the build-up and the final sting), keeping just enough between them for \
the story to make sense. If you open on a flash-forward, what follows must pay it off quickly and must not \
re-stage suspense the opening already resolved. 35-55 seconds is the sweet spot: one hook, one or two \
escalations, one cliffhanger. Every second must earn its place.

Watch out for:
- Episodes often end warm or resolved. If this one does, cut earlier, on an unresolved question, threat or decision.
- Moments that resolve (a triumphant speech, a completed rescue, an escape) feel climactic but leave nothing hanging.
- Episodes often open by replaying the previous episode's ending (see CONTINUITY). Prefer moments that are new here.
- Keep the lines that state who people are to each other ("my sister", "your husband"); they let a stranger follow.
- Loud is not legible: a shouting match where you can't tell who is wronged, or why, loses cold viewers.
- Lines that only make sense with earlier episodes (unexplained names, callbacks) lose cold viewers.
- Spoilers: don't reveal a hidden identity, its proof and the comeback all at once, don't show a villain's \
downfall, and don't answer a mystery the show is still building. Tease it instead."""


def render_script(blocks: list[Block], scenes: list[dict]) -> str:
    headings = {s["index"]: s.get("heading") for s in scenes}
    out = []
    scene = None
    for b in blocks:
        if b.scene != scene:
            scene = b.scene
            heading = headings.get(scene)
            out.append(f"=== SCENE {scene}{' - ' + heading if heading else ''} ===")
        span = f"[{b.id}] {fmt_tc(b.start)}-{fmt_tc(b.end)}"
        if b.kind == "dialogue":
            who = b.speaker or "VOICE"
            if b.offscreen:
                who += " [off-screen]"
            if b.emotion:
                who += f" ({b.emotion})"
            out.append(f'{span} {who}: "{b.text}"')
        else:
            out.append(f"{span} {b.kind.upper()}: {b.text}")
    return "\n".join(out)


def picker_prompt(*, show: str, episode_label: str, duration: float, logline: str | None,
                  continuity: str | None, script: str) -> str:
    endings = "\n".join(f"  {key}: {text}" for key, text in config.CLIFFHANGER_TYPES.items())
    return f"""\
SHOW: {show}
{episode_label} - runtime {fmt_tc(duration)}
LOGLINE: {logline or "(none)"}
CONTINUITY: {continuity or "(none)"}

SCRIPT
Each block is "[id] start-end KIND: text". CAMERA blocks describe the shot and overlap in time with the \
ACTION and dialogue they show.
{script}

TASK
Propose up to {config.MAX_CANDIDATES} distinct promo candidates from this episode, strongest first. Make them \
genuinely different (different moments, or a clearly different cut), not near-duplicates.

Rules for every candidate:
- 1 to {config.MAX_SEGMENTS} segments, listed in play order. A segment is a block range: it starts at \
start_block's start time, ends at end_block's end time, and includes everything in between.
- Total duration across segments: {config.MIN_PROMO_SEC:.0f}-{config.MAX_PROMO_SEC:.0f} seconds.
- hook_block must start within the first {config.HOOK_WINDOW_SEC:.0f} seconds of the promo, so the first \
segment should start at, or just before, the hook.
- cliffhanger_block must be in the last segment, at or very near its end.
- Segments must not overlap.
- hook and cliffhanger: quote the script's words (or describe the action) exactly as written.
- cliffhanger_type, one of:
{endings}
- risks: anything that makes the promo a bad choice to post: a spoiler (see above), graphic violence (gore, \
torture, injury close-ups - not a slap or a shove) or sexual content that ad platforms may reject. Empty list \
if none."""


def picker_schema() -> dict:
    segment = {
        "type": "object",
        "properties": {
            "start_block": {"type": "integer", "description": "First block id in the segment"},
            "end_block": {"type": "integer", "description": "Last block id in the segment"},
        },
        "required": ["start_block", "end_block"],
    }
    candidate = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Catchy 2-6 word promo title"},
            "segments": {"type": "array", "items": segment, "minItems": 1, "maxItems": config.MAX_SEGMENTS},
            "hook_block": {"type": "integer"},
            "hook": {"type": "string", "description": "What the viewer sees or hears in the first 3 seconds"},
            "hook_type": {"type": "string", "enum": config.HOOK_TYPES},
            "cliffhanger_block": {"type": "integer"},
            "cliffhanger": {"type": "string", "description": "The final beat the promo cuts on"},
            "cliffhanger_type": {"type": "string", "enum": list(config.CLIFFHANGER_TYPES)},
            "open_question": {"type": "string", "description": "The question the cut leaves the viewer asking"},
            "why": {"type": "string", "description": "One line on why this promo works"},
            "risks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": RISK_TYPES},
                        "note": {"type": "string", "description": "One short sentence"},
                    },
                    "required": ["type", "note"],
                },
            },
        },
        "required": [
            "title", "segments", "hook_block", "hook", "hook_type", "cliffhanger_block", "cliffhanger",
            "cliffhanger_type", "open_question", "why", "risks",
        ],
    }
    return {
        "type": "object",
        "properties": {
            "candidates": {"type": "array", "items": candidate, "minItems": 1, "maxItems": config.MAX_CANDIDATES},
        },
        "required": ["candidates"],
    }


def repair_prompt(problems: dict[int, list[str]]) -> str:
    lines = [
        "Some candidates break the rules. Fix them by changing their block ranges, hook_block or "
        "cliffhanger_block (you may also replace a candidate with a better valid one). Keep valid candidates "
        "unchanged. Return the complete corrected JSON.",
        "",
    ]
    for index, issues in problems.items():
        lines.append(f"Candidate {index + 1}:")
        lines.extend(f"- {issue}" for issue in issues)
    return "\n".join(lines)


JUDGE_SYSTEM = f"""\
You are two people at once: a first-time viewer scrolling TikTok, and the performance-marketing lead of a \
microdrama app who decides which promos get paid spend. You have NEVER seen this show. Judge only what is in \
each clip - assume the viewer knows nothing that the clip itself does not show or say. Many viewers scroll with \
the sound off, so weigh what's on screen (CAMERA / ACTION lines) as well as the dialogue.

For each candidate, first write viewer_question: the specific question the ending leaves a viewer needing \
answered, in your own words. If there isn't one, leave it empty and score cliffhanger at most \
{config.NO_QUESTION_CLIFFHANGER_CAP}.

Then, for every dimension, write the rationale first (at most 25 words, citing the specific moment), then the \
score from 1 to 10 using the anchors. Use the full range: a 5 is a usable but forgettable promo, and most clips \
are not 9s. Score each candidate on its own merits; do not force a spread between candidates."""


def judge_prompt(transcripts: list[tuple[str, float, int, str]]) -> str:
    rubric = []
    for d in config.DIMENSIONS:
        rubric.append(f"{d['key']} - {d['question']}")
        rubric.extend(f"  {score}: {text}" for score, text in d["anchors"].items())
    clips = []
    for label, duration, n_segments, text in transcripts:
        noun = "segment" if n_segments == 1 else "segments"
        clips.append(f"CANDIDATE {label} ({duration:.1f}s, {n_segments} {noun})\n{text}")
    rubric_text = "\n".join(rubric)
    clips_text = "\n\n".join(clips)
    return f"""\
Each candidate below is the complete transcript of a promo clip, timed from the start of the clip. CAMERA, \
ACTION and SFX lines are what the viewer sees and hears; quoted lines are dialogue. "--- CUT ---" marks a jump \
to a different moment. The hook dimension is about 00:00-00:03 only.

RUBRIC
{rubric_text}

{clips_text}

For every candidate return: viewer_question; a score with rationale for every dimension; "confusions" - things \
a first-time viewer would not understand (names, relationships or situations the clip references but never \
explains, or jumps that don't follow; empty list if none); and the clip's dominant tone."""


def judge_schema(labels: list[str]) -> dict:
    score = {
        "type": "object",
        "properties": {
            "rationale": {"type": "string"},
            "score": {"type": "integer", "minimum": 1, "maximum": 10},
        },
        "required": ["rationale", "score"],
    }
    judgment = {
        "type": "object",
        "properties": {
            "candidate": {"type": "string", "enum": labels},
            "viewer_question": {"type": "string"},
            "scores": {
                "type": "object",
                "properties": {key: score for key in config.DIMENSION_KEYS},
                "required": list(config.DIMENSION_KEYS),
            },
            "confusions": {"type": "array", "items": {"type": "string"}},
            "tone": {"type": "string", "enum": config.TONES},
        },
        "required": ["candidate", "viewer_question", "scores", "confusions", "tone"],
    }
    return {
        "type": "object",
        "properties": {"judgments": {"type": "array", "items": judgment, "minItems": len(labels)}},
        "required": ["judgments"],
    }
