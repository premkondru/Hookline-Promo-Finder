"""Deterministic stand-in for Gemini (run.py --fake, and tests). No network, no key.

It reads the block list out of the picker prompt and proposes simple, usually-valid windows; the judge
returns hash-derived scores so different clips get different, stable numbers.
"""

from __future__ import annotations

import hashlib
import json
import re

from .. import config
from .base import LLMResult

_LINE_RE = re.compile(r"^\[(\d+)\] (\d+):(\d+\.\d+)-(\d+):(\d+\.\d+) (.+?): (.*)$")
_CANDIDATE_RE = re.compile(r"^CANDIDATE ([A-Z]) \(", re.MULTILINE)


def _num(seed: str, low: int, high: int) -> int:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return low + digest[0] % (high - low + 1)


class FakeProvider:
    name = "fake"

    def close(self) -> None:
        pass

    def list_models(self) -> list[str]:
        return list(config.MODEL_IDS)

    def generate_json(self, *, model, system, messages, schema, thinking_level=None) -> LLMResult:
        if "candidates" in schema.get("properties", {}):
            data = self._pick(messages[0][1])
        else:
            labels = schema["properties"]["judgments"]["items"]["properties"]["candidate"]["enum"]
            data = self._judge(messages[-1][1], labels)
        return LLMResult(data=data, raw_text=json.dumps(data), usage={}, model_version=f"fake:{model}")

    def _pick(self, prompt: str) -> dict:
        lines = []
        for raw in prompt.splitlines():
            if m := _LINE_RE.match(raw):
                start = int(m.group(2)) * 60 + float(m.group(3))
                end = int(m.group(4)) * 60 + float(m.group(5))
                is_dialogue = m.group(6) not in ("CAMERA", "ACTION", "SFX")
                lines.append((int(m.group(1)), start, end, is_dialogue, m.group(7)))
        dialogue = [line for line in lines if line[3]]
        if len(dialogue) < 2:
            dialogue = lines
        candidates = []

        # A: the last ~38s, ending on the final line (episodes are written to end on a cliffhanger).
        last = dialogue[-1]
        first = next((d for d in dialogue if d[1] >= last[2] - 38), dialogue[0])
        candidates.append(self._candidate("The Final Turn", first, last))

        # B: the first ~30s of the episode.
        opening = dialogue[0]
        close = next((d for d in dialogue if d[2] >= opening[1] + 30), dialogue[-1])
        if close[0] != last[0]:
            candidates.append(self._candidate("Cold Open", opening, close))
        return {"candidates": candidates}

    @staticmethod
    def _candidate(title, first, last) -> dict:
        return {
            "title": title,
            "segments": [{"start_block": first[0], "end_block": last[0]}],
            "hook_block": first[0],
            "hook": first[4][:120],
            "hook_type": "threat_or_insult",
            "cliffhanger_block": last[0],
            "cliffhanger": last[4][:120],
            "cliffhanger_type": "pre_result",
            "open_question": "What happens next?",
            "why": "Fake pick: opens on a line and cuts on the scene's final beat.",
            "risks": [],
        }

    def _judge(self, prompt: str, labels: list[str]) -> dict:
        parts = _CANDIDATE_RE.split(prompt)
        bodies = {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}
        judgments = []
        for label in labels:
            body = bodies.get(label, label)
            scores = {
                key: {"rationale": f"Fake rationale for {key}.", "score": _num(key + body, 3, 9)}
                for key in config.DIMENSION_KEYS
            }
            confusions = ["Who are these people to each other?"] if _num("c" + body, 0, 2) == 0 else []
            judgments.append(
                {
                    "candidate": label,
                    "viewer_question": "" if _num("q" + body, 0, 5) == 0 else "What happens next?",
                    "scores": scores,
                    "confusions": confusions,
                    "tone": config.TONES[_num("t" + body, 0, len(config.TONES) - 1)],
                }
            )
        return {"judgments": judgments}
