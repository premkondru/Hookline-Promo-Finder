"""Turns the picker's block ranges into exact, clean, rule-checked promo segments.

The LLM never writes timestamps. It names script blocks; this module converts them to the
script's own timecodes, snaps cuts so no line is clipped, and checks the promo rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import config
from .screenplay import Block

EPS = 0.01
# Lines we never cut in the middle of. Action blocks are protected only when snapping is short,
# because some action blocks describe long continuous movement.
_MAX_ACTION_SNAP_SEC = 2.0
# How far the end may be extended to finish the current shot (a held reaction after the last line).
_MAX_SHOT_EXTEND_SEC = 1.0
_MIN_LINE_OVERLAP_SEC = 0.3


def fmt_tc(seconds: float) -> str:
    """64.5 -> '01:04.50' (the script's own MM:SS.ss format)."""
    seconds = max(0.0, round(seconds, 2))
    minutes = int(seconds // 60)
    return f"{minutes:02d}:{seconds - minutes * 60:05.2f}"


def fmt_clock(seconds: float) -> str:
    """Promo-relative time for transcripts: 5.4 -> '00:05.4'."""
    seconds = max(0.0, round(seconds, 1))
    minutes = int(seconds // 60)
    return f"{minutes:02d}:{seconds - minutes * 60:04.1f}"


@dataclass
class Segment:
    start: float
    end: float
    start_block: int
    end_block: int

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 3)

    def to_json(self) -> dict:
        return {
            "start_sec": round(self.start, 3),
            "end_sec": round(self.end, 3),
            "start": fmt_tc(self.start),
            "end": fmt_tc(self.end),
            "duration_sec": round(self.duration, 2),
            "start_block": self.start_block,
            "end_block": self.end_block,
        }


@dataclass
class Resolved:
    """A candidate after conversion to times and rule checks."""

    segments: list[Segment] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)  # {"level", "code", "message"}
    hook_offset: float | None = None  # promo-relative start of the hook block

    @property
    def duration(self) -> float:
        return round(sum(s.duration for s in self.segments), 2)

    @property
    def valid(self) -> bool:
        return not self.errors


def _straddles(block: Block, t: float) -> bool:
    return block.start < t - EPS and t < block.end - EPS


def _snap_start(t: float, blocks: list[Block]) -> float:
    """Move a start back so it doesn't begin mid-line. A cut inside a line's last fraction of a second is left
    alone: scripts often overlap consecutive lines by 0.1-0.2s, and snapping there would drag in the previous
    line and push the hook late."""
    for _ in range(20):
        moved = False
        for b in blocks:
            if not _straddles(b, t) or b.end - t <= _MIN_LINE_OVERLAP_SEC:
                continue
            if b.kind == "dialogue" or (b.kind == "action" and t - b.start <= _MAX_ACTION_SNAP_SEC):
                t, moved = b.start, True
        if not moved:
            break
    return t


def _snap_end(t: float, blocks: list[Block]) -> float:
    """Move an end forward so it doesn't cut a line off (ignoring lines that have only just begun)."""
    for _ in range(20):
        moved = False
        for b in blocks:
            if not _straddles(b, t) or t - b.start <= _MIN_LINE_OVERLAP_SEC:
                continue
            if b.kind == "dialogue" or (b.kind == "action" and b.end - t <= _MAX_ACTION_SNAP_SEC):
                t, moved = b.end, True
        if not moved:
            break
    return t


def _extend_to_shot_end(t: float, blocks: list[Block], limit: float) -> float:
    """Finish the shot we're in if it ends soon (a held reaction after the last line), without starting a new
    line or running into the next segment."""
    shot_ends = [b.end for b in blocks if b.kind == "camera" and _straddles(b, t) and b.end - t <= _MAX_SHOT_EXTEND_SEC]
    if not shot_ends:
        return t
    extended = min(max(shot_ends), limit)
    if extended <= t + EPS:
        return t
    if any(b.kind == "dialogue" and t - EPS <= b.start < extended - EPS for b in blocks):
        return t
    return extended


def resolve(
    blocks: list[Block],
    picks: list[tuple[int, int]],
    hook_block: int | None,
    cliffhanger_block: int | None,
) -> Resolved:
    """Convert block-id ranges to snapped segments and check the promo rules."""
    res = Resolved()
    by_id = {b.id: b for b in blocks}

    if not picks:
        res.errors.append("No segments given.")
        return res
    if len(picks) > config.MAX_SEGMENTS:
        res.errors.append(f"{len(picks)} segments; the maximum is {config.MAX_SEGMENTS}.")

    for n, (a, z) in enumerate(picks, start=1):
        if a not in by_id or z not in by_id:
            res.errors.append(f"Segment {n} uses unknown block ids ({a}..{z}); valid ids are 1..{len(blocks)}.")
            continue
        if z < a:
            res.errors.append(f"Segment {n}: end_block {z} comes before start_block {a}.")
            continue
        start = _snap_start(by_id[a].start, blocks)
        end = _snap_end(by_id[z].end, blocks)
        if end - start < config.MIN_SEGMENT_SEC:
            res.errors.append(f"Segment {n} is {end - start:.1f}s long; each segment needs at least {config.MIN_SEGMENT_SEC:.0f}s.")
            continue
        res.segments.append(Segment(start=start, end=end, start_block=a, end_block=z))

    if res.errors:
        return res

    # Hold each segment's last shot where possible, but never into the start of another segment.
    for seg in res.segments:
        later_starts = [o.start for o in res.segments if o is not seg and o.start >= seg.end - EPS]
        seg.end = _extend_to_shot_end(seg.end, blocks, min(later_starts, default=float("inf")))
    res.segments = merge_contiguous(res.segments)

    ordered = sorted(res.segments, key=lambda s: s.start)
    for prev, nxt in zip(ordered, ordered[1:]):
        if nxt.start < prev.end - EPS:
            res.errors.append(
                f"Segments overlap: {fmt_tc(prev.start)}-{fmt_tc(prev.end)} and {fmt_tc(nxt.start)}-{fmt_tc(nxt.end)}."
            )
    if ordered != res.segments:
        res.warnings.append(_flag("info", "flash_forward", "Segments play out of story order (flash-forward opening)."))

    total = res.duration
    if total < config.MIN_PROMO_SEC:
        res.errors.append(f"Total duration is {total:.1f}s; it must be at least {config.MIN_PROMO_SEC:.0f}s.")
    elif total > config.MAX_PROMO_SEC:
        res.errors.append(f"Total duration is {total:.1f}s; it must be at most {config.MAX_PROMO_SEC:.0f}s.")

    hook = by_id.get(hook_block) if hook_block is not None else None
    if hook is None:
        res.errors.append(f"hook_block {hook_block} is not a block in this script.")
    else:
        offset = promo_offset(res.segments, hook.start)
        if offset is None:
            res.errors.append(f"hook_block {hook.id} ({fmt_tc(hook.start)}) is outside the promo's segments.")
        else:
            res.hook_offset = round(offset, 2)
            if offset > config.HOOK_WINDOW_SEC + EPS:
                res.errors.append(
                    f"The hook (block {hook.id}) lands {offset:.1f}s into the promo; it must start within "
                    f"{config.HOOK_WINDOW_SEC:.0f}s. Start the first segment closer to it."
                )

    cliff = by_id.get(cliffhanger_block) if cliffhanger_block is not None else None
    if cliff is None:
        res.errors.append(f"cliffhanger_block {cliffhanger_block} is not a block in this script.")
    elif res.segments:
        last = res.segments[-1]
        if not (last.start - EPS <= cliff.start < last.end):
            res.errors.append(f"cliffhanger_block {cliff.id} is not inside the last segment.")
        else:
            tail = last.end - min(cliff.end, last.end)
            if tail > config.MAX_TAIL_AFTER_CLIFFHANGER_SEC:
                res.warnings.append(
                    _flag("warn", "tail_after_cliffhanger", f"Keeps running {tail:.1f}s after the cliffhanger beat.")
                )

    short = [s for s in res.segments if s.duration < 3.0]
    if short and len(res.segments) > 1:
        res.warnings.append(_flag("warn", "short_segment", "Contains a very short segment (<3s), which can feel choppy."))
    return res


def merge_contiguous(segments: list[Segment]) -> list[Segment]:
    """Join segments that play back to back with no gap: they're one continuous stretch, not a cut."""
    merged: list[Segment] = []
    for seg in segments:
        if merged and abs(seg.start - merged[-1].end) <= EPS:
            merged[-1] = Segment(merged[-1].start, seg.end, merged[-1].start_block, seg.end_block)
        else:
            merged.append(seg)
    return merged


def _flag(level: str, code: str, message: str) -> dict:
    return {"level": level, "code": code, "message": message}


def promo_offset(segments: list[Segment], source_time: float) -> float | None:
    """Map a script time to promo-relative time, or None if it's not in the promo."""
    offset = 0.0
    for seg in segments:
        if seg.start - EPS <= source_time < seg.end:
            return offset + max(0.0, source_time - seg.start)
        offset += seg.duration
    return None


def promo_lines(blocks: list[Block], segments: list[Segment], keep_ids: set[int] | None = None) -> list[dict]:
    """Every block inside the promo, in play order, with promo-relative times clamped to its segment."""
    keep_ids = keep_ids or set()
    lines = []
    offset = 0.0
    for index, seg in enumerate(segments):
        inside = []
        for b in blocks:
            # The hook and cliffhanger always show (even a zero-length block from a timestamp typo).
            if b.id in keep_ids and seg.start - EPS <= b.start < seg.end:
                inside.append(b)
            elif min(b.end, seg.end) - max(b.start, seg.start) >= _MIN_LINE_OVERLAP_SEC:
                inside.append(b)
        inside.sort(key=lambda b: (max(b.start, seg.start), b.id))
        for b in inside:
            lines.append(
                {
                    "id": b.id,
                    "kind": b.kind,
                    "speaker": b.speaker,
                    "emotion": b.emotion,
                    "text": b.text,
                    "src_start": b.start,
                    "src_end": b.end,
                    "t_start": round(offset + max(b.start, seg.start) - seg.start, 2),
                    "t_end": round(offset + min(b.end, seg.end) - seg.start, 2),
                    "segment": index,
                }
            )
        offset += seg.duration
    return lines


def longest_silence(lines: list[dict], total: float) -> tuple[float, float, float]:
    """Longest promo-relative stretch with no dialogue: (seconds, from, to). Visual-only stretches play as dead
    air on a scrolling feed, and the judge tends not to penalize them."""
    spoken = sorted((l["t_start"], l["t_end"]) for l in lines if l["kind"] == "dialogue")
    best = (0.0, 0.0, 0.0)
    cursor = 0.0
    for start, end in spoken + [(total, total)]:
        if start - cursor > best[0]:
            best = (round(start - cursor, 2), round(cursor, 2), round(start, 2))
        cursor = max(cursor, end)
    return best


def transcript(lines: list[dict], total: float) -> str:
    """What a first-time viewer gets: promo-relative times, visuals and dialogue, cuts marked."""
    out = []
    segment = 0
    for line in lines:
        if line["segment"] != segment:
            segment = line["segment"]
            out.append("--- CUT ---")
        stamp = f"[{fmt_clock(line['t_start'])}]"
        if line["kind"] == "dialogue":
            who = line["speaker"] or "VOICE"
            if line["emotion"]:
                who += f" ({line['emotion']})"
            out.append(f'{stamp} {who}: "{line["text"]}"')
        else:
            out.append(f"{stamp} {line['kind'].upper()}: {line['text']}")
    out.append(f"[{fmt_clock(total)}] END OF CLIP")
    return "\n".join(out)
