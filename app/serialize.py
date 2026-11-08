"""DB rows -> API JSON (and pipeline results -> DB values)."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import asdict

from .db import PROMO_COLUMNS
from .pipeline import EpisodeInput, PromoResult
from .screenplay import blocks_from_json
from .timeline import Segment, promo_lines

POST_FIRST_COUNT = 3
EARLY_FRACTION = 1 / 3
# A promo with any of these flags isn't recommended for posting first, whatever its score.
BLOCKING_FLAG_CODES = {"out_of_spec", "spoiler", "ad_policy", "weak_hook", "weak_cliffhanger"}
# Hook and cliffhanger are the brief's must-haves; an equal-weight average can hide a failed one
# (a hook of 2 with five 8s still averages 7), so a score at or below this raises a flag.
MUST_HAVE_FLOOR = 4
_MUST_HAVES = {"hook": "Weak hook", "cliffhanger": "Weak cliffhanger"}


def episode_input(row) -> EpisodeInput:
    return EpisodeInput(
        show_title=row["show_title"],
        episode_label=row["episode_label"],
        logline=row["logline"],
        continuity_notes=row["continuity_notes"],
        blocks=blocks_from_json(json.loads(row["blocks_json"])),
        scenes=json.loads(row["scenes_json"]),
    )


_JSON_FIELDS = {
    "segments_json": "segments",
    "scores_json": "scores",
    "flags_json": "flags",
    "confusions_json": "confusions",
    "candidates_json": "candidates",
    "meta_json": "meta",
}


def promo_values(result: PromoResult) -> dict:
    d = asdict(result)
    return {
        column: json.dumps(d[_JSON_FIELDS[column]]) if column in _JSON_FIELDS else d[column]
        for column in PROMO_COLUMNS
    }


def must_have_flags(scores: dict) -> list[dict]:
    return [
        {"level": "warn", "code": f"weak_{key}", "message": f"{label} ({scores[key]['score']}/10) despite the average."}
        for key, label in _MUST_HAVES.items()
        if key in scores and scores[key]["score"] <= MUST_HAVE_FLOOR
    ]


def promo_summary(row, rank: int | None = None) -> dict:
    scores = json.loads(row["scores_json"])
    return {
        "id": row["id"],
        "episode_id": row["episode_id"],
        "rank": rank,
        "post_first": False,
        "show_title": row["show_title"],
        "episode_number": row["episode_number"],
        "episode_label": row["episode_label"],
        "title": row["title"],
        "hook": row["hook"],
        "hook_type": row["hook_type"],
        "cliffhanger": row["cliffhanger"],
        "cliffhanger_type": row["cliffhanger_type"],
        "open_question": row["open_question"],
        "why": row["why"],
        "duration_sec": row["duration_sec"],
        "segments": [
            {k: s[k] for k in ("start_sec", "end_sec", "start", "end", "duration_sec")}
            for s in json.loads(row["segments_json"])
        ],
        "scores": {k: v["score"] for k, v in scores.items()},
        "composite": row["composite"],
        "flags": json.loads(row["flags_json"]) + must_have_flags(scores),
        "tone": row["tone"],
        "picker_model": row["picker_model"],
        "judge_model": row["judge_model"],
        "created_at": row["created_at"],
    }


def promo_detail(row, blocks_json: list[dict]) -> dict:
    out = promo_summary(row)
    scores = json.loads(row["scores_json"])
    segments = [
        Segment(start=s["start_sec"], end=s["end_sec"], start_block=s["start_block"], end_block=s["end_block"])
        for s in json.loads(row["segments_json"])
    ]
    keep = {row["hook_block"], row["cliffhanger_block"]}
    out.update(
        {
            "rationales": {k: v.get("rationale", "") for k, v in scores.items()},
            "viewer_question": row["viewer_question"],
            "confusions": json.loads(row["confusions_json"]),
            "logline": row["logline"],
            "episode_duration_sec": row["episode_duration_sec"],
            "source_filename": row["source_filename"],
            "hook_line_id": row["hook_block"],
            "cliffhanger_line_id": row["cliffhanger_block"],
            "lines": promo_lines(blocks_from_json(blocks_json), segments, keep_ids=keep),
            "candidates": json.loads(row["candidates_json"]),
        }
    )
    return out


def duplicate_pairs(rows) -> dict[int, list[tuple[int, str, int]]]:
    """Promos of the same show that repeat most of each other's dialogue: an episode's recap of the previous
    cliffhanger, or two episodes ending on the same sting. Returns id -> [(other id, other label, shared lines)]."""
    prints = []
    for row in rows:
        lines = set(json.loads(row["meta_json"] or "{}").get("dialogue") or [])
        if lines:
            prints.append((row["id"], row["show_title"], row["episode_label"], lines))
    pairs: dict[int, list[tuple[int, str, int]]] = defaultdict(list)
    for i, (id_a, show_a, label_a, a) in enumerate(prints):
        for id_b, show_b, label_b, b in prints[i + 1:]:
            shared = len(a & b)
            if show_a == show_b and shared >= 3 and shared >= 0.5 * min(len(a), len(b)):
                pairs[id_a].append((id_b, label_b, shared))
                pairs[id_b].append((id_a, label_a, shared))
    return pairs


def duplicate_flags(rows) -> dict[int, list[dict]]:
    return {
        promo_id: [
            {
                "level": "warn",
                "code": "duplicate",
                "message": f"Repeats {shared} lines of the {label} promo (recap or shared sting); post one.",
            }
            for _, label, shared in others
        ]
        for promo_id, others in duplicate_pairs(rows).items()
    }


def ranked(rows) -> list[dict]:
    """Summaries in composite order (rows arrive sorted) with duplicate flags, plus, within each show: rank and
    the post-first picks. Ranking per show keeps the list and the detail page consistent with several shows.

    Post first = the POST_FIRST_COUNT highest-scoring promos that have no blocking flag and don't repeat a promo
    already picked, preferring the first EARLY_FRACTION of the series: a new viewer starts at episode 1, so a
    promo from early on promises what they'll get soon after installing, while late-series payoffs spoil the
    story and sit deep behind the paywall. Later episodes only fill in when too few early ones qualify."""
    pairs = duplicate_pairs(rows)
    flags = duplicate_flags(rows)
    rank_in_show: dict[str, int] = defaultdict(int)
    last_episode: dict[str, int] = defaultdict(int)
    out = []
    for row in rows:
        show = row["show_title"]
        rank_in_show[show] += 1
        last_episode[show] = max(last_episode[show], row["episode_number"] or 0)
        summary = promo_summary(row, rank=rank_in_show[show])
        summary["flags"].extend(flags.get(row["id"], []))
        out.append(summary)

    def blocked(s: dict) -> bool:
        return any(f["level"] == "error" or f["code"] in BLOCKING_FLAG_CODES for f in s["flags"])

    def early(s: dict) -> bool:
        return bool(s["episode_number"]) and s["episode_number"] <= math.ceil(
            last_episode[s["show_title"]] * EARLY_FRACTION
        )

    for show in rank_in_show:
        picked: set[int] = set()
        for allowed in (early, lambda s: True):
            for s in out:
                if len(picked) == POST_FIRST_COUNT:
                    break
                if s["show_title"] != show or s["id"] in picked or blocked(s) or not allowed(s):
                    continue
                if any(other in picked for other, _, _ in pairs.get(s["id"], [])):
                    continue
                picked.add(s["id"])
                s["post_first"] = True
    return out


def tray_item(row) -> dict:
    return {k: row[k] for k in ("id", "show_title", "episode_number", "episode_label", "status", "error",
                                "source_filename", "created_at")}
