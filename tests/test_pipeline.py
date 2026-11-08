import json

import pytest

from app import config
from app.llm import LLMResult, ProviderError
from app.llm.fake import FakeProvider
from app.pipeline import EpisodeInput, PipelineError, analyze
from app.screenplay import parse_screenplay

from .conftest import EPISODE_FILES


def episode(text: str) -> EpisodeInput:
    sp = parse_screenplay(text)
    return EpisodeInput("Show", sp.episode_label, sp.logline, sp.continuity_notes, sp.blocks, sp.scenes)


def find(ep, text):
    return next(b for b in ep.blocks if b.text == text)


class Scripted:
    """Replays canned responses; each entry is a dict or a callable(schema) -> dict."""

    name = "scripted"

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def generate_json(self, *, model, system, messages, schema, thinking_level=None):
        self.calls.append({"model": model, "messages": messages, "schema": schema})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        data = item(schema) if callable(item) else item
        return LLMResult(data=data, raw_text=json.dumps(data))

    def list_models(self):
        return []

    def close(self):
        pass


def cand(start, end, hook, cliff, title="Cut"):
    return {
        "title": title,
        "segments": [{"start_block": start.id, "end_block": end.id}],
        "hook_block": hook.id,
        "hook": hook.text,
        "hook_type": "shocking_line",
        "cliffhanger_block": cliff.id,
        "cliffhanger": cliff.text,
        "open_question": "?",
        "why": "because",
    }


def judgment(label, score, tone="romance", confusions=(), question="Will she say yes?"):
    return {
        "candidate": label,
        "viewer_question": question,
        "scores": {k: {"rationale": f"{k} reason", "score": score} for k in config.DIMENSION_KEYS},
        "confusions": list(confusions),
        "tone": tone,
    }


@pytest.fixture
def ep3(ep_text):
    ep = episode(ep_text(3))
    rescue = cand(
        next(b for b in ep.blocks if b.kind == "camera" and b.start == 68.1),
        find(ep, "Because I want to."),
        find(ep, "Take your hands off her."),
        find(ep, "Because I want to."),
        "The Rescue",
    )
    guards_action = next(b for b in ep.blocks if b.kind == "action" and b.start == 58.2)
    guards = cand(guards_action, find(ep, "...let her go."), find(ep, "Guards! Remove her!"), find(ep, "...let her go."),
                  "Guards!")
    whole = cand(ep.blocks[0], ep.blocks[-1], ep.blocks[0], ep.blocks[-1], "Everything")
    return ep, rescue, guards, whole


def test_fake_provider_runs_every_episode():
    for path in EPISODE_FILES:
        result = analyze(episode(path.read_text(encoding="utf-8")), FakeProvider(), "m", "m")
        assert 1 <= result.composite <= 10
        assert config.MIN_PROMO_SEC <= result.duration_sec <= config.MAX_PROMO_SEC
        assert not any(f["code"] == "out_of_spec" for f in result.flags)


def test_selects_highest_composite_and_keeps_all_candidates(ep3):
    ep, rescue, guards, _ = ep3
    provider = Scripted({"candidates": [rescue, guards]}, {"judgments": [judgment("A", 6), judgment("B", 8)]})
    result = analyze(ep, provider, "picker-m", "judge-m")
    assert result.title == "Guards!"
    assert result.composite == 8
    assert [c["selected"] for c in result.candidates] == [False, True]
    assert result.segments[0]["start"] == "00:58.20"
    assert [c["model"] for c in provider.calls] == ["picker-m", "judge-m"]
    # The judge sees only clip transcripts, never the episode's logline.
    judge_prompt = provider.calls[1]["messages"][-1][1]
    assert ep.logline not in judge_prompt and "CANDIDATE A" in judge_prompt and "CANDIDATE B" in judge_prompt


def test_invalid_candidates_get_one_repair_round(ep3):
    ep, rescue, _, whole = ep3
    provider = Scripted({"candidates": [whole]}, {"candidates": [rescue]}, {"judgments": [judgment("A", 7)]})
    result = analyze(ep, provider, "m", "m")
    assert len(provider.calls) == 3
    repair_messages = provider.calls[1]["messages"]
    assert [role for role, _ in repair_messages] == ["user", "model", "user"]
    assert "at most 60" in repair_messages[-1][1]
    assert result.title == "The Rescue"
    assert any(f["code"] == "repaired" for f in result.flags)
    assert not any(f["code"] == "out_of_spec" for f in result.flags)


def test_repair_round_keeps_valid_first_round_candidates(ep3):
    ep, rescue, guards, whole = ep3
    provider = Scripted(
        {"candidates": [rescue, whole]},
        {"candidates": [guards]},
        {"judgments": [judgment("A", 6), judgment("B", 8)]},
    )
    result = analyze(ep, provider, "m", "m")
    assert [c["title"] for c in result.candidates] == ["The Rescue", "Guards!"]
    assert result.title == "Guards!" and any(f["code"] == "repaired" for f in result.flags)


def test_still_invalid_repair_is_not_called_repaired(ep_text):
    ep = episode(ep_text(1))
    bad = cand(ep.blocks[0], ep.blocks[-1], ep.blocks[0], ep.blocks[-1])
    worse = cand(ep.blocks[1], ep.blocks[-1], ep.blocks[1], ep.blocks[-1])
    provider = Scripted({"candidates": [bad]}, {"candidates": [worse]}, {"judgments": [judgment("A", 5), judgment("B", 4)]})
    result = analyze(ep, provider, "m", "m")
    codes = [f["code"] for f in result.flags]
    assert "out_of_spec" in codes and "repaired" not in codes


def test_malformed_llm_values_never_crash(ep3):
    ep, rescue, _, _ = ep3
    junk = {**rescue, "segments": "nope", "hook_block": float("inf"), "risks": "lots", "hook_type": ["x"],
            "cliffhanger_type": {"a": 1}}
    with pytest.raises(PipelineError):  # no usable candidate, but a clean error rather than a TypeError
        analyze(ep, Scripted({"candidates": [junk]}, {"candidates": "broken"}), "m", "m")

    j = judgment("A", 7)
    j["confusions"] = "Who is the stranger?"  # a string, not a list
    odd = {**rescue, "risks": "lots", "hook_type": ["x"], "cliffhanger_type": {"a": 1}}
    result = analyze(ep, Scripted({"candidates": [odd]}, {"judgments": [j]}), "m", "m")
    assert result.confusions == [] and result.hook_type == "other" and result.cliffhanger_type == "other"

    j = judgment("A", 7)
    j["scores"]["hook"]["score"] = float("inf")
    with pytest.raises(PipelineError):
        analyze(ep, Scripted({"candidates": [rescue]}, {"judgments": [j]}), "m", "m")


def test_out_of_spec_is_flagged_not_hidden(ep_text):
    ep = episode(ep_text(1))
    first, last = ep.blocks[0], ep.blocks[-1]
    bad = cand(first, last, first, last)
    provider = Scripted({"candidates": [bad]}, {"candidates": [bad]}, {"judgments": [judgment("A", 5)]})
    result = analyze(ep, provider, "m", "m")
    assert any(f["code"] == "out_of_spec" and f["level"] == "error" for f in result.flags)


def test_judge_confusions_and_low_clarity_become_flags(ep3):
    ep, rescue, _, _ = ep3
    j = judgment("A", 7, confusions=["Who is the stranger?"])
    j["scores"]["clarity"]["score"] = 3
    result = analyze(ep, Scripted({"candidates": [rescue]}, {"judgments": [j]}), "m", "m")
    codes = [f["code"] for f in result.flags]
    assert "cold_viewer" in codes and "needs_context" in codes
    assert result.confusions == ["Who is the stranger?"]


def test_judge_skipping_a_candidate_still_picks_from_the_rest(ep3):
    ep, rescue, guards, _ = ep3
    result = analyze(ep, Scripted({"candidates": [rescue, guards]}, {"judgments": [judgment("B", 6)]}), "m", "m")
    assert result.title == "Guards!"


def test_provider_errors_propagate(ep3):
    ep, *_ = ep3
    with pytest.raises(ProviderError):
        analyze(ep, Scripted(ProviderError("boom", kind="quota")), "m", "m")


def test_picker_risks_become_flags(ep3):
    ep, rescue, _, _ = ep3
    rescue = {**rescue, "risks": [{"type": "spoiler", "note": "Shows the villain's arrest."},
                                  {"type": "graphic_violence", "note": "A punch."},
                                  {"type": "made_up", "note": "ignored"}]}
    result = analyze(ep, Scripted({"candidates": [rescue]}, {"judgments": [judgment("A", 7)]}), "m", "m")
    messages = {f["code"]: f["message"] for f in result.flags}
    assert messages["spoiler"] == "Spoiler risk: Shows the villain's arrest."
    assert messages["ad_policy"].startswith("Graphic violence")
    assert "made_up" not in str(result.flags)


def test_dialogue_fingerprint_saved_for_duplicate_detection(ep3):
    ep, rescue, _, _ = ep3
    result = analyze(ep, Scripted({"candidates": [rescue]}, {"judgments": [judgment("A", 7)]}), "m", "m")
    assert "take your hands off her" in result.meta["dialogue"]


def test_weak_must_haves_are_flagged_even_when_the_average_is_fine():
    from app.serialize import must_have_flags

    scores = {k: {"score": 8, "rationale": ""} for k in config.DIMENSION_KEYS}
    assert must_have_flags(scores) == []
    scores["hook"]["score"] = 2
    flags = must_have_flags(scores)
    assert [f["code"] for f in flags] == ["weak_hook"] and "2/10" in flags[0]["message"]


def test_duplicate_flags_pair_promos_within_a_show():
    from app.serialize import duplicate_flags

    lines = json.dumps({"dialogue": ["you stole my wedding", "now it is mine", "guards remove her now"]})
    rows = [
        {"id": 1, "show_title": "S", "episode_label": "Episode 1", "meta_json": lines},
        {"id": 2, "show_title": "S", "episode_label": "Episode 2", "meta_json": lines},
        {"id": 3, "show_title": "Other", "episode_label": "Episode 2", "meta_json": lines},
        {"id": 4, "show_title": "S", "episode_label": "Episode 9", "meta_json": json.dumps({"dialogue": ["x y z"]})},
    ]
    flags = duplicate_flags(rows)
    assert set(flags) == {1, 2}
    assert "Episode 2" in flags[1][0]["message"] and flags[1][0]["code"] == "duplicate"


def test_cliffhanger_capped_when_judge_cannot_name_the_open_question(ep3):
    ep, rescue, _, _ = ep3
    result = analyze(ep, Scripted({"candidates": [rescue]}, {"judgments": [judgment("A", 9, question="")]}), "m", "m")
    assert result.scores["cliffhanger"]["score"] == config.NO_QUESTION_CLIFFHANGER_CAP
    assert result.scores["hook"]["score"] == 9
    assert any(f["code"] == "no_open_question" for f in result.flags)
    assert result.viewer_question == ""


def test_scores_are_clamped(ep3):
    ep, rescue, _, _ = ep3
    j = judgment("A", 7)
    j["scores"]["hook"]["score"] = 14
    result = analyze(ep, Scripted({"candidates": [rescue]}, {"judgments": [j]}), "m", "m")
    assert result.scores["hook"]["score"] == 10
