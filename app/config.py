"""Static configuration: paths, promo rules, scoring dimensions and models."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
SEED_DIR = BASE_DIR / "seed"
SEED_EPISODES_DIR = SEED_DIR / "episodes"
# Snapshot of a finished analysis run, used by eval/compare.py (never loaded into the app).
RUN_SNAPSHOT_FILE = BASE_DIR / "eval" / "run_promos.json"
DEFAULT_DATA_DIR = BASE_DIR / "data"

# Promo rules from the brief.
MIN_PROMO_SEC = 20.0
MAX_PROMO_SEC = 60.0
HOOK_WINDOW_SEC = 3.0
MAX_SEGMENTS = 3
MAX_CANDIDATES = 3
MIN_SEGMENT_SEC = 2.0
# A promo should cut on the cliffhanger, not linger after it.
MAX_TAIL_AFTER_CLIFFHANGER_SEC = 6.0
# Longest stretch without dialogue before a promo is flagged for dead air.
MAX_SILENCE_SEC = 6.0

PROMPT_VERSION = "2026-11-07.3"

# Scoring dimensions. The radar has one vertex per entry; the judge's JSON schema is built from this list.
# Anchors describe what a 2 / 5 / 8 / 10 looks like so independent episodes are scored on the same scale.
DIMENSIONS = [
    {
        "key": "hook",
        "label": "Hook",
        "question": "Would a scroller stop in the first 3 seconds?",
        "anchors": {
            2: "Opens on setup, travel, exposition or an establishing shot; the first conflict comes after ~5s.",
            5: "Conflict in the first line, but generic, or it's unclear who is being wronged.",
            8: "Within 1-2 lines: visible humiliation or aggression, a threat, or a discovered betrayal; "
               "who-versus-whom reads even on mute.",
            10: "The first beat is a trope-defining provocation (a slap, a public shaming, a stunning reveal) that also "
                "shows the relationship; it reads on mute and on audio alone.",
        },
    },
    {
        "key": "cliffhanger",
        "label": "Cliffhanger",
        "question": "Does the last beat leave a question you need answered?",
        "anchors": {
            2: "Ends on the payoff, a lull or a resolved beat; no open question.",
            5: "Ends tense, but the open question is vague or low-stakes.",
            8: "Ends just before a specific result lands (an answer, a blow, a reveal, an arrival), with the last "
               "line complete.",
            10: "Ends on the story's central question at peak tension; the viewer can say exactly what they need "
                "to see next.",
        },
    },
    {
        "key": "clarity",
        "label": "Clarity",
        "question": "Can a first-time viewer follow who's who and what's at stake?",
        "anchors": {
            2: "Depends on unseen events: unexplained names, callbacks or relationships; or the jumps between "
               "moments confuse.",
            5: "The gist lands, but the stakes or a key relationship would need a caption.",
            8: "Within about 8 seconds a newcomer knows who is wronged, by whom, and the trope; any jumps between "
               "moments are easy to follow.",
            10: "The clip alone conveys the premise and every relationship it relies on.",
        },
    },
    {
        "key": "stakes",
        "label": "Stakes",
        "question": "How intense is the conflict or emotion?",
        "anchors": {
            2: "Low-stakes chatter or logistics.",
            5: "Real conflict, but muted, abstract, or loud without being legible.",
            8: "High emotional stakes: humiliation, betrayal, danger or love on the line, and you feel it.",
            10: "Life, identity or love hangs in the balance, played at full intensity; you're invested in seconds.",
        },
    },
    {
        "key": "momentum",
        "label": "Momentum",
        "question": "Does it escalate with no dead air?",
        "anchors": {
            2: "Flat: repetition, exposition, or the tension drops after the hook.",
            5: "One escalation, with slack lines or a jarring jump.",
            8: "Each beat raises the stakes toward a reversal; any jumps between moments feel natural.",
            10: "An unbroken rise toward a promised reversal; every line moves the conflict.",
        },
    },
    {
        "key": "premise",
        "label": "Premise pull",
        "question": "Does it sell the series' core fantasy, not just one scene?",
        "anchors": {
            2: "No sense of what the series is about or why to binge it.",
            5: "Hints at the premise without making it the draw.",
            8: "Clearly sells a bingeable fantasy or trope (e.g. a jilted bride rescued by a mysterious man).",
            10: "A perfect trailer for the series' core fantasy, promising more of what the show delivers.",
        },
    },
]
# Rubric rule enforced in code: if the blind judge can't name the question the ending leaves open,
# the cliffhanger can't score above this.
NO_QUESTION_CLIFFHANGER_CAP = 4
DIMENSION_KEYS = [d["key"] for d in DIMENSIONS]
# Equal weights by default; change here to weight the composite.
DIMENSION_WEIGHTS = {d["key"]: 1.0 for d in DIMENSIONS}

TONES = ["betrayal", "romance", "revenge", "danger", "triumph", "mystery", "grief"]
# Opening and ending taxonomies, after how ReelShort / DramaBox promos are cut (see docs/RESEARCH.md).
HOOK_TYPES = [
    "humiliation",       # public shaming, mockery, kneeling
    "violence",          # slap, shove, blow, mid-action aggression
    "threat_or_insult",  # a line that lands on audio alone
    "betrayal",          # betrayal or abandonment discovered
    "reveal",            # identity, status or secret revealed or teased
    "danger",            # danger or mystery in medias res
    "romance",           # proposal, romantic ultimatum, forced intimacy
    "spectacle",
    "other",
]
CLIFFHANGER_TYPES = {
    "pre_result": "cuts just before an answer, blow or reveal lands",
    "twist_line": "cuts right after a line that flips a relationship or identity",
    "next_event": "cuts on the threshold of an arrival, a summons or a door opening",
    "emotional_peak": "cuts at the height of an emotion with the outcome open",
    "new_question": "answers the opening's question, then opens a new one",
    "other": "anything else",
}

# Hardcoded model menu (verified against the Gemini model list on 2026-11-07).
# thinking: thinking_level per pipeline stage; every level used here is valid for that model.
MODELS = [
    {
        "id": "gemini-3.8-flash",
        "label": "Gemini 3.8 Flash",
        "note": "Default: strongest Flash model, good speed",
        "thinking": {"picker": "high", "judge": "medium"},
    },
    {
        "id": "gemini-4-argon",
        "label": "Gemini 4 Argon",
        "note": "Flagship reasoning: slowest, paid tier only",
        "thinking": {"picker": "high", "judge": "medium"},
    },
    {
        "id": "gemini-3.6-flash",
        "label": "Gemini 3.6 Flash",
        "note": "Previous-generation Flash",
        "thinking": {"picker": "high", "judge": "medium"},
    },
    {
        "id": "gemini-3.5-flash-lite",
        "label": "Gemini 3.5 Flash-Lite",
        "note": "Fastest and cheapest",
        "thinking": {"picker": "medium", "judge": "low"},
    },
]
MODEL_IDS = [m["id"] for m in MODELS]
DEFAULT_MODEL = "gemini-3.8-flash"

# Background analysis.
WORKER_CONCURRENCY = 5
# Per attempt. The SDK also sends this as the server-side deadline, and a "high"-thinking pick can take
# ~3 minutes, so a shorter value turns slow-but-fine calls into 504s.
LLM_TIMEOUT_MS = 600_000
LLM_MAX_OUTPUT_TOKENS = 32_768

# Upload limits (files are only ever read into memory, never written to disk).
MAX_TXT_BYTES = 2 * 1024 * 1024
MAX_ZIP_BYTES = 25 * 1024 * 1024
MAX_ZIP_ENTRIES = 500
MAX_ZIP_TOTAL_BYTES = 60 * 1024 * 1024

UNTITLED_SHOW = "Untitled show"
