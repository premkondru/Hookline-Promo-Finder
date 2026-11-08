"""Screenplay normalization, hashing and parsing.

Scripts look like:

    EPISODE NUMBER: Episode 3
    EPISODE LOGLINE: ...
    CONTINUITY NOTES: ...
    --- SCRIPT START ---
    SCENE 01
    Scene heading: INT. CATHEDRAL - DAY
    ...
    **CAMERA:**
    Start: (00:00.00) | End: (00:03.50)
    Medium shot on Lady Juliana ...

    **LADY JULIANA (Hurt, Bitter):**
    Start: (00:08.80) | End: (00:10.80)
    "You stole my wedding."
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass, field

_TS_RE = re.compile(r"^Start:\s*\((\d+):(\d{1,2}(?:\.\d+)?)\)\s*\|\s*End:\s*\((\d+):(\d{1,2}(?:\.\d+)?)\)\s*$")
_BLOCK_RE = re.compile(r"^\*\*(.+?):\*\*\s*$")
_SCENE_RE = re.compile(r"^SCENE\s+(\d+)\s*$", re.IGNORECASE)
_HEADING_RE = re.compile(r"^Scene heading:\s*(.*)$", re.IGNORECASE)
_EP_NUM_RE = re.compile(r"(\d+)")
_FILENAME_EP_RE = re.compile(r"episode[-_ ]?0*(\d+)", re.IGNORECASE)
_OFFSCREEN_TAGS = {"O.S.", "V.O.", "O.C.", "CONT'D", "CONT\u2019D"}

MIN_BLOCKS = 5


class ScreenplayError(ValueError):
    """The text is not a screenplay we can work with."""


@dataclass
class Block:
    id: int
    kind: str  # dialogue | action | camera | sfx
    text: str
    start: float
    end: float
    scene: int
    speaker: str | None = None
    emotion: str | None = None
    offscreen: bool = False


@dataclass
class Screenplay:
    episode_label: str | None
    episode_number: int | None
    logline: str | None
    continuity_notes: str | None
    scenes: list[dict] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max((b.end for b in self.blocks), default=0.0)

    def blocks_json(self) -> list[dict]:
        return [asdict(b) for b in self.blocks]


def decode_bytes(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="strict")


def normalize_text(text: str) -> str:
    """Canonical form used for hashing and storage, so the same script saved with a BOM,
    CRLF line endings or trailing spaces is still recognized as the same episode."""
    text = unicodedata.normalize("NFC", text.lstrip("\ufeff"))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip("\n") + "\n"


def content_hash(normalized: str) -> str:
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _seconds(minutes: str, seconds: str) -> float:
    return round(int(minutes) * 60 + float(seconds), 3)


def _split_speaker(label: str) -> tuple[str, str | None, bool]:
    name = label.split("(", 1)[0].strip()
    tags = [t.strip() for t in re.findall(r"\(([^)]*)\)", label)]
    offscreen = any(t.upper() in _OFFSCREEN_TAGS for t in tags)
    emotion = ", ".join(t for t in tags if t and t.upper() not in _OFFSCREEN_TAGS) or None
    return name, emotion, offscreen


def _kind(label: str) -> str:
    upper = label.strip().upper()
    if upper == "CAMERA":
        return "camera"
    if upper == "ACTION":
        return "action"
    if upper.startswith(("SOUND", "SFX", "MUSIC")):
        return "sfx"
    return "dialogue"


def _strip_quotes(text: str) -> str:
    text = text.strip()
    pairs = [('"', '"'), ("\u201c", "\u201d")]
    for left, right in pairs:
        if len(text) >= 2 and text.startswith(left) and text.endswith(right):
            return text[1:-1].strip()
    return text


def _header_value(lines: list[str], key: str) -> str | None:
    prefix = key.upper() + ":"
    for line in lines[:15]:
        if line.upper().startswith(prefix):
            return line[len(prefix):].strip() or None
    return None


def parse_screenplay(text: str, filename: str | None = None) -> Screenplay:
    lines = normalize_text(text).split("\n")
    episode_label = _header_value(lines, "EPISODE NUMBER")
    episode_number = None
    if episode_label and (m := _EP_NUM_RE.search(episode_label)):
        episode_number = int(m.group(1))
    elif filename and (m := _FILENAME_EP_RE.search(filename)):
        episode_number = int(m.group(1))
    if episode_label is None and episode_number is not None:
        episode_label = f"Episode {episode_number}"

    sp = Screenplay(
        episode_label=episode_label,
        episode_number=episode_number,
        logline=_header_value(lines, "EPISODE LOGLINE"),
        continuity_notes=_header_value(lines, "CONTINUITY NOTES"),
    )

    scene_index = 0
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if m := _SCENE_RE.match(line):
            scene_index = len(sp.scenes) + 1
            sp.scenes.append({"index": scene_index, "number": int(m.group(1)), "heading": None})
            i += 1
            continue
        if (m := _HEADING_RE.match(line)) and sp.scenes:
            sp.scenes[-1]["heading"] = m.group(1).strip() or None
            i += 1
            continue
        block_match = _BLOCK_RE.match(line)
        ts_match = _TS_RE.match(lines[i + 1].strip()) if block_match and i + 1 < len(lines) else None
        if not ts_match:
            i += 1
            continue
        label = block_match.group(1).strip()
        start = _seconds(ts_match.group(1), ts_match.group(2))
        end = _seconds(ts_match.group(3), ts_match.group(4))
        text_lines = []
        j = i + 2
        while j < len(lines):
            nxt = lines[j].strip()
            if not nxt or _BLOCK_RE.match(nxt) or _SCENE_RE.match(nxt) or nxt.startswith("--- SCRIPT"):
                break
            text_lines.append(nxt)
            j += 1
        body = " ".join(text_lines).strip()
        kind = _kind(label)
        block = Block(
            id=len(sp.blocks) + 1,
            kind=kind,
            text=_strip_quotes(body) if kind == "dialogue" else body,
            start=start,
            end=max(end, start),
            scene=scene_index,
        )
        if kind == "dialogue":
            block.speaker, block.emotion, block.offscreen = _split_speaker(label)
        sp.blocks.append(block)
        i = j

    if len(sp.blocks) < MIN_BLOCKS:
        raise ScreenplayError(
            f"Found {len(sp.blocks)} timed blocks; expected a screenplay with "
            "'**CAMERA:**' / '**NAME (Emotion):**' blocks followed by 'Start: (MM:SS.ss) | End: (MM:SS.ss)' lines."
        )
    return sp


def blocks_from_json(items: list[dict]) -> list[Block]:
    return [Block(**item) for item in items]
