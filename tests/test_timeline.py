from app.screenplay import Block, parse_screenplay
from app.timeline import fmt_tc, promo_lines, promo_offset, resolve, transcript


def line(id_, start, end, kind="dialogue"):
    return Block(id=id_, kind=kind, text=f"line {id_}", start=start, end=end, scene=1,
                 speaker="A" if kind == "dialogue" else None)


def test_tiny_line_overlaps_dont_drag_in_neighbours():
    # Consecutive lines overlapping by 0.2s, as scripts often do.
    blocks = [line(1, 0.0, 5.0), line(2, 4.8, 10.0), line(3, 10.0, 26.0), line(4, 25.8, 30.0)]
    res = resolve(blocks, [(2, 3)], 2, 3)
    assert res.valid, res.errors
    assert res.segments[0].start == 4.8 and res.hook_offset == 0  # not snapped back to line 1
    assert res.segments[0].end == 26.0  # line 4 has only just begun; not pulled in


def test_shot_hold_never_runs_into_the_next_segment():
    blocks = [
        line(1, 9.0, 20.0), line(2, 20.0, 30.0), line(3, 30.0, 40.0), line(4, 39.5, 40.8, kind="camera"),
        line(5, 40.3, 45.0, kind="action"), line(6, 45.0, 52.0),
    ]
    # Segment 1 ends at 40.0 inside a camera shot that runs to 40.8; segment 2 starts at 40.3.
    res = resolve(blocks, [(1, 3), (5, 6)], 1, 6)
    assert res.valid, res.errors  # previously: a false "Segments overlap" error
    # The hold is clamped at 40.3, which makes the two back to back, so they merge into one stretch.
    assert [(s.start, s.end) for s in res.segments] == [(9.0, 52.0)]


def test_longest_silence_and_dead_air_flag():
    from app.pipeline import dead_air_flag
    from app.timeline import longest_silence

    lines = [
        {"kind": "dialogue", "t_start": 0.5, "t_end": 3.0},
        {"kind": "action", "t_start": 3.0, "t_end": 12.0},
        {"kind": "dialogue", "t_start": 12.4, "t_end": 14.0},
    ]
    assert longest_silence(lines, 18.0) == (9.4, 3.0, 12.4)
    flag = dead_air_flag(lines, 18.0)
    assert flag["code"] == "dead_air" and "9.4s" in flag["message"]
    assert dead_air_flag(lines[:1] + [{"kind": "dialogue", "t_start": 4.0, "t_end": 9.0}], 12.0) is None


def test_back_to_back_segments_merge_into_one():
    blocks = [line(1, 0.0, 12.0), line(2, 12.0, 25.0), line(3, 25.0, 31.0)]
    res = resolve(blocks, [(1, 1), (2, 3)], 1, 3)
    assert res.valid, res.errors
    assert [(s.start, s.end, s.start_block, s.end_block) for s in res.segments] == [(0.0, 31.0, 1, 3)]


def test_zero_length_hook_block_still_appears_in_lines():
    blocks = [line(1, 0.0, 0.0, kind="action"), line(2, 0.0, 12.0), line(3, 12.0, 25.0)]
    res = resolve(blocks, [(1, 3)], 1, 3)
    lines = promo_lines(blocks, res.segments, keep_ids={1, 3})
    assert lines[0]["id"] == 1


def blocks_of(ep_text, n):
    return parse_screenplay(ep_text(n)).blocks


def find(blocks, text):
    return next(b for b in blocks if b.text == text)


def test_fmt_tc():
    assert fmt_tc(0) == "00:00.00"
    assert fmt_tc(64.5) == "01:04.50"
    assert fmt_tc(145.75) == "02:25.75"


def test_valid_single_segment(ep_text):
    blocks = blocks_of(ep_text, 3)
    hook = find(blocks, "Take your hands off her.")  # 01:09.90
    cliff = find(blocks, "Because I want to.")  # 01:52.80-01:54.10
    start = next(b for b in blocks if b.kind == "camera" and b.start == 68.1)
    res = resolve(blocks, [(start.id, cliff.id)], hook.id, cliff.id)
    assert res.valid, res.errors
    assert 20 <= res.duration <= 60
    assert res.hook_offset is not None and res.hook_offset <= 3


def test_end_snaps_to_finish_dialogue(ep_text):
    blocks = blocks_of(ep_text, 1)
    # Camera block 00:54.60-00:57.60 ends while "You let me believe..." (00:57.00-01:00.00) is mid-line.
    cam = next(b for b in blocks if b.kind == "camera" and b.start == 54.6)
    first = blocks[0]
    res = resolve(blocks, [(first.id, cam.id)], first.id, cam.id)
    seg = res.segments[0]
    assert seg.end >= 60.0  # extended to the end of the line, not cut at 57.60


def test_start_snaps_back_to_line_start(ep_text):
    blocks = blocks_of(ep_text, 1)
    # Camera block starting at 00:57.60 begins mid-line ("You let me believe..." starts 00:57.00).
    cam = next(b for b in blocks if b.kind == "camera" and b.start == 57.6)
    last = find(blocks, "Of course I knew.")
    res = resolve(blocks, [(cam.id, last.id)], cam.id, last.id)
    assert res.segments[0].start == 57.0


def test_rule_violations(ep_text):
    blocks = blocks_of(ep_text, 1)
    ids = {b.start: b.id for b in blocks}
    first, last = blocks[0].id, blocks[-1].id

    too_long = resolve(blocks, [(first, last)], first, last)
    assert any("at most 60" in e for e in too_long.errors)

    a, z = ids[0.0], ids[6.8]
    too_short = resolve(blocks, [(a, z)], a, z)
    assert any("at least 20" in e for e in too_short.errors)

    late_hook = find(blocks, "Because he is marrying me.")
    res = resolve(blocks, [(ids[11.0], late_hook.id)], late_hook.id, late_hook.id)
    assert any("lands" in e for e in res.errors)

    overlap = resolve(blocks, [(ids[11.0], ids[33.7]), (ids[29.8], ids[43.9])], ids[11.0], ids[43.9])
    assert any("overlap" in e for e in overlap.errors)

    unknown = resolve(blocks, [(0, 9999)], 1, 1)
    assert any("unknown block" in e for e in unknown.errors)

    cliff_outside = resolve(blocks, [(ids[11.0], ids[41.5])], ids[11.0], first)
    assert any("not inside the last segment" in e for e in cliff_outside.errors)


def test_flash_forward_two_segments(ep_text):
    blocks = blocks_of(ep_text, 1)
    shock = find(blocks, "Because he is marrying me.")  # 00:39.10
    setup_start = next(b for b in blocks if b.start == 11.0)
    setup_end = find(blocks, "Why are you holding her hand?")
    cliff = find(blocks, "You let me come here...")
    res = resolve(blocks, [(shock.id, cliff.id), (setup_start.id, setup_end.id)], shock.id, setup_end.id)
    assert res.valid, res.errors
    assert any(w["code"] == "flash_forward" for w in res.warnings)


def test_promo_lines_are_promo_relative(ep_text):
    blocks = blocks_of(ep_text, 1)
    shock = find(blocks, "Because he is marrying me.")
    cliff = find(blocks, "You let me come here...")
    s1 = next(b for b in blocks if b.start == 11.0)
    s1_end = find(blocks, "Not anymore.")
    res = resolve(blocks, [(s1.id, s1_end.id), (shock.id, cliff.id)], s1.id, cliff.id)
    assert res.valid, res.errors
    lines = promo_lines(blocks, res.segments)
    assert lines[0]["t_start"] == 0
    assert {l["segment"] for l in lines} == {0, 1}
    seg0_len = res.segments[0].duration
    first_seg1 = next(l for l in lines if l["segment"] == 1)
    assert abs(first_seg1["t_start"] - seg0_len) < 0.05
    assert all(0 <= l["t_start"] <= l["t_end"] <= res.duration + 0.01 for l in lines)
    assert promo_offset(res.segments, shock.start) is not None
    text = transcript(lines, res.duration)
    assert "--- CUT ---" in text and text.splitlines()[0].startswith("[00:00.0]")
