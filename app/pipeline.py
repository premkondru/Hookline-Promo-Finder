"""Episode -> best promo: pick candidates, validate (and repair), judge them blind, keep the best."""

from __future__ import annotations

import logging
import math
import re
import time
from dataclasses import dataclass, field

from . import config, prompts
from .llm import LLMProvider, LLMResult, ProviderError
from .screenplay import Block
from .timeline import Resolved, fmt_clock, longest_silence, promo_lines, resolve, transcript

log = logging.getLogger(__name__)

_RISK_FLAGS = {
    "spoiler": ("spoiler", "Spoiler risk"),
    "graphic_violence": ("ad_policy", "Graphic violence may be restricted in paid ads"),
    "sexual_content": ("ad_policy", "Sexual content may be restricted in paid ads"),
}


class PipelineError(RuntimeError):
    """Analysis failed in a way worth showing to the user."""


@dataclass
class EpisodeInput:
    show_title: str
    episode_label: str
    logline: str | None
    continuity_notes: str | None
    blocks: list[Block]
    scenes: list[dict]

    @property
    def duration(self) -> float:
        return max((b.end for b in self.blocks), default=0.0)


@dataclass
class Candidate:
    index: int
    pick: dict
    resolved: Resolved
    repaired: bool = False
    label: str | None = None
    lines: list[dict] = field(default_factory=list)
    judgment: dict | None = None
    composite: float | None = None

    @property
    def cut(self) -> tuple:
        return tuple((round(s.start, 2), round(s.end, 2)) for s in self.resolved.segments)


@dataclass
class PromoResult:
    title: str
    hook: str
    hook_type: str
    cliffhanger: str
    cliffhanger_type: str
    open_question: str
    viewer_question: str
    why: str
    segments: list[dict]
    duration_sec: float
    scores: dict
    composite: float
    flags: list[dict]
    confusions: list[str]
    tone: str
    hook_block: int
    cliffhanger_block: int
    candidates: list[dict]
    picker_model: str
    judge_model: str
    meta: dict


def thinking_level(model: str, stage: str) -> str | None:
    for m in config.MODELS:
        if m["id"] == model:
            return m.get("thinking", {}).get(stage)
    return None


def composite_of(scores: dict) -> float:
    weights = config.DIMENSION_WEIGHTS
    total = sum(weights[k] for k in config.DIMENSION_KEYS)
    return round(sum(scores[k]["score"] * weights[k] for k in config.DIMENSION_KEYS) / total, 2)


# LLM output is untrusted even with a schema: every field read goes through one of these.

def _as_int(value) -> int | None:
    if isinstance(value, bool) or (isinstance(value, float) and not math.isfinite(value)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _as_list(value) -> list:
    return value if isinstance(value, list) else []


def _as_text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _choice(value, options, default: str) -> str:
    return value if isinstance(value, str) and value in options else default


def _parse_candidates(data: dict, blocks: list[Block]) -> list[Candidate]:
    raw = data.get("candidates") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        raise PipelineError("The picker's answer had no candidate list.")
    out = []
    for item in raw[: config.MAX_CANDIDATES]:
        if not isinstance(item, dict):
            continue
        picks = []
        for seg in _as_list(item.get("segments")):
            if isinstance(seg, dict):
                a, z = _as_int(seg.get("start_block")), _as_int(seg.get("end_block"))
                if a is not None and z is not None:
                    picks.append((a, z))
        hook_block = _as_int(item.get("hook_block"))
        cliff_block = _as_int(item.get("cliffhanger_block"))
        out.append(Candidate(index=len(out), pick=item, resolved=resolve(blocks, picks, hook_block, cliff_block)))
    if not out:
        raise PipelineError("The picker returned no candidates.")
    return out


def _merge(original: list[Candidate], repaired: list[Candidate]) -> list[Candidate]:
    """Keep every valid first-round candidate, add the repair round's valid ones that are new cuts. If nothing is
    valid at all, keep everything so the best effort can still be judged (and flagged out of spec)."""
    merged = [c for c in original if c.resolved.valid]
    seen = {c.cut for c in merged}
    for c in repaired:
        if c.resolved.valid and c.cut not in seen:
            c.repaired = True
            merged.append(c)
            seen.add(c.cut)
    if not merged:
        cuts = {c.cut for c in original}
        merged = original + [c for c in repaired if c.cut not in cuts]
    merged = merged[: len(prompts.CANDIDATE_LABELS)]
    for i, c in enumerate(merged):
        c.index = i
    return merged


def _call(provider: LLMProvider, usage: list, stage: str, **kwargs) -> LLMResult:
    started = time.monotonic()
    result = provider.generate_json(**kwargs)
    usage.append({"stage": stage, "seconds": round(time.monotonic() - started, 1), **result.usage})
    return result


def _judgment(j: dict) -> dict | None:
    """Validate one judge entry: every dimension needs an integer score. Applies the no-open-question cap."""
    raw_scores = j.get("scores")
    if not isinstance(raw_scores, dict):
        return None
    scores = {}
    for key in config.DIMENSION_KEYS:
        entry = raw_scores.get(key)
        score = _as_int(entry.get("score")) if isinstance(entry, dict) else None
        if score is None:
            return None
        scores[key] = {"score": max(1, min(10, score)), "rationale": _as_text(entry.get("rationale"))}
    question = _as_text(j.get("viewer_question"))
    cap = config.NO_QUESTION_CLIFFHANGER_CAP
    if not question and "cliffhanger" in scores and scores["cliffhanger"]["score"] > cap:
        scores["cliffhanger"]["score"] = cap
        scores["cliffhanger"]["rationale"] += f" (Capped at {cap}: no open question to name.)"
    return {
        "scores": scores,
        "viewer_question": question,
        "confusions": [text for x in _as_list(j.get("confusions")) if (text := _as_text(x))],
        "tone": _choice(j.get("tone"), config.TONES, config.TONES[0]),
    }


def analyze(ep: EpisodeInput, provider: LLMProvider, picker_model: str, judge_model: str) -> PromoResult:
    usage: list[dict] = []
    script = prompts.render_script(ep.blocks, ep.scenes)
    messages = [
        (
            "user",
            prompts.picker_prompt(
                show=ep.show_title,
                episode_label=ep.episode_label,
                duration=ep.duration,
                logline=ep.logline,
                continuity=ep.continuity_notes,
                script=script,
            ),
        )
    ]
    common = {"system": prompts.PICKER_SYSTEM, "schema": prompts.picker_schema()}
    first = _call(
        provider, usage, "pick", model=picker_model, messages=messages,
        thinking_level=thinking_level(picker_model, "picker"), **common,
    )
    candidates = _parse_candidates(first.data, ep.blocks)

    problems = {c.index: c.resolved.errors for c in candidates if c.resolved.errors}
    if problems:
        repair_messages = messages + [("model", first.raw_text), ("user", prompts.repair_prompt(problems))]
        repaired: list[Candidate] = []
        try:
            second = _call(
                provider, usage, "repair", model=picker_model, messages=repair_messages,
                thinking_level=thinking_level(picker_model, "picker"), **common,
            )
            repaired = _parse_candidates(second.data, ep.blocks)
        except ProviderError as exc:
            if exc.pauses_queue:
                raise
            log.warning("Repair round failed for %s: %s", ep.episode_label, exc)
        except Exception as exc:  # a malformed repair answer must not cost the valid first round
            log.warning("Repair answer unusable for %s: %s", ep.episode_label, exc)
        candidates = _merge(candidates, repaired)

    valid = [c for c in candidates if c.resolved.valid]
    out_of_spec = not valid
    judged = (valid or [c for c in candidates if c.resolved.segments])[: len(prompts.CANDIDATE_LABELS)]
    if not judged:
        issues = "; ".join(e for c in candidates for e in c.resolved.errors)
        raise PipelineError(f"No usable promo candidates: {issues}")

    for label, c in zip(prompts.CANDIDATE_LABELS, judged):
        c.label = label
        keep = {_as_int(c.pick.get("hook_block")), _as_int(c.pick.get("cliffhanger_block"))} - {None}
        c.lines = promo_lines(ep.blocks, c.resolved.segments, keep_ids=keep)
    labels = [c.label for c in judged]
    judge_input = [
        (c.label, c.resolved.duration, len(c.resolved.segments), transcript(c.lines, c.resolved.duration))
        for c in judged
    ]
    verdict = _call(
        provider, usage, "judge", model=judge_model, system=prompts.JUDGE_SYSTEM,
        messages=[("user", prompts.judge_prompt(judge_input))], schema=prompts.judge_schema(labels),
        thinking_level=thinking_level(judge_model, "judge"),
    )
    by_label: dict[str, dict] = {}
    for j in _as_list(verdict.data.get("judgments") if isinstance(verdict.data, dict) else None):
        if isinstance(j, dict) and isinstance(j.get("candidate"), str) and j["candidate"] in labels:
            by_label.setdefault(j["candidate"], j)

    for c in judged:
        if (j := by_label.get(c.label)) and (judgment := _judgment(j)):
            c.judgment = judgment
            c.composite = composite_of(judgment["scores"])

    scored = [c for c in judged if c.judgment]
    if not scored:
        raise PipelineError("The judge didn't return usable scores for any candidate.")
    best = max(
        scored,
        key=lambda c: (
            c.composite,
            c.judgment["scores"].get("hook", {}).get("score", 0),
            c.judgment["scores"].get("cliffhanger", {}).get("score", 0),
            -c.index,
        ),
    )
    return _result(best, candidates, out_of_spec, picker_model, judge_model, usage)


def _result(best: Candidate, candidates, out_of_spec, picker_model, judge_model, usage) -> PromoResult:
    pick, res, judgment = best.pick, best.resolved, best.judgment
    flags = []
    if out_of_spec:
        flags.extend({"level": "error", "code": "out_of_spec", "message": e} for e in res.errors)
    flags.extend(res.warnings)
    if best.repaired:
        flags.append({"level": "info", "code": "repaired", "message": "Picker fixed this cut after a rule check."})
    if res.hook_offset is not None:
        flags.append({"level": "info", "code": "hook_timing", "message": f"Hook lands at {res.hook_offset:.1f}s."})
    if dead_air := dead_air_flag(best.lines, res.duration):
        flags.append(dead_air)
    clarity = judgment["scores"].get("clarity", {}).get("score")
    if clarity is not None and clarity <= 4:
        flags.append({"level": "warn", "code": "needs_context", "message": "A first-time viewer may be lost."})
    if not judgment["viewer_question"]:
        flags.append(
            {"level": "warn", "code": "no_open_question", "message": "A cold viewer couldn't name what's left open."}
        )
    flags.extend({"level": "warn", "code": "cold_viewer", "message": q} for q in judgment["confusions"])
    for risk in _as_list(pick.get("risks")):
        if isinstance(risk, dict) and (kind := _choice(risk.get("type"), _RISK_FLAGS, "")):
            code, prefix = _RISK_FLAGS[kind]
            note = _as_text(risk.get("note"))
            flags.append({"level": "warn", "code": code, "message": f"{prefix}{': ' + note if note else ''}"})

    candidate_summaries = [
        {
            "label": c.label,
            "title": _as_text(c.pick.get("title")),
            "selected": c is best,
            "valid": c.resolved.valid,
            "repaired": c.repaired,
            "composite": c.composite,
            "scores": {k: v["score"] for k, v in (c.judgment or {}).get("scores", {}).items()},
            "segments": [s.to_json() for s in c.resolved.segments],
            "duration_sec": c.resolved.duration,
            "hook": _as_text(c.pick.get("hook")),
            "cliffhanger": _as_text(c.pick.get("cliffhanger")),
            "why": _as_text(c.pick.get("why")),
            "issues": c.resolved.errors + [w["message"] for w in c.resolved.warnings],
        }
        for c in candidates
    ]
    return PromoResult(
        title=_as_text(pick.get("title")) or "Untitled promo",
        hook=_as_text(pick.get("hook")),
        hook_type=_choice(pick.get("hook_type"), config.HOOK_TYPES, "other"),
        cliffhanger=_as_text(pick.get("cliffhanger")),
        cliffhanger_type=_choice(pick.get("cliffhanger_type"), config.CLIFFHANGER_TYPES, "other"),
        open_question=_as_text(pick.get("open_question")),
        viewer_question=judgment["viewer_question"],
        why=_as_text(pick.get("why")),
        segments=[s.to_json() for s in res.segments],
        duration_sec=res.duration,
        scores=judgment["scores"],
        composite=best.composite,
        flags=flags,
        confusions=judgment["confusions"],
        tone=judgment["tone"],
        hook_block=_as_int(pick.get("hook_block")) or 0,
        cliffhanger_block=_as_int(pick.get("cliffhanger_block")) or 0,
        candidates=candidate_summaries,
        picker_model=picker_model,
        judge_model=judge_model,
        meta={"calls": usage, "prompt_version": config.PROMPT_VERSION, "dialogue": dialogue_fingerprint(best.lines)},
    )


def dead_air_flag(lines: list[dict], duration: float) -> dict | None:
    gap, start, end = longest_silence(lines, duration)
    if gap <= config.MAX_SILENCE_SEC:
        return None
    return {
        "level": "warn",
        "code": "dead_air",
        "message": f"{gap:.1f}s with no dialogue ({fmt_clock(start)}-{fmt_clock(end)}).",
    }


def dialogue_fingerprint(lines: list[dict]) -> list[str]:
    """Normalized dialogue lines of a promo, used to spot promos that repeat each other (recaps, shared stings)."""
    out = set()
    for line in lines:
        if line["kind"] == "dialogue":
            words = re.sub(r"[^a-z0-9 ]+", " ", line["text"].lower()).split()
            if len(words) >= 3:
                out.add(" ".join(words))
    return sorted(out)
