import pytest

from app.screenplay import ScreenplayError, content_hash, decode_bytes, normalize_text, parse_screenplay

from .conftest import EPISODE_FILES


def test_all_bundled_episodes_parse():
    assert len(EPISODE_FILES) == 50
    total = 0
    for path in EPISODE_FILES:
        sp = parse_screenplay(path.read_text(encoding="utf-8"), path.name)
        total += len(sp.blocks)
        assert sp.episode_number is not None and sp.episode_label == f"Episode {sp.episode_number}"
        assert sp.logline and sp.scenes
        assert 60 < sp.duration < 210
        assert [b.id for b in sp.blocks] == list(range(1, len(sp.blocks) + 1))
        for b in sp.blocks:
            assert b.end >= b.start
            assert b.text
            assert (b.speaker is not None) == (b.kind == "dialogue")
    assert total == 3727


def test_episode_numbers_match_filenames():
    numbers = [parse_screenplay(p.read_text(encoding="utf-8"), p.name).episode_number for p in EPISODE_FILES]
    assert numbers == list(range(1, 51))


def test_block_details(ep_text):
    sp = parse_screenplay(ep_text(3))
    stranger = next(b for b in sp.blocks if b.text == "I can...")
    assert stranger.speaker == "THE BEARDED STRANGER"
    assert stranger.emotion == "Deep, Resonant"
    assert stranger.offscreen
    first = sp.blocks[0]
    assert (first.kind, first.start, first.end) == ("camera", 0.0, 3.5)
    line = next(b for b in sp.blocks if b.kind == "dialogue")
    assert line.text == "Look at you..."  # surrounding quotes stripped
    assert sp.scenes[0]["heading"].startswith("INT. CATHEDRAL")


def test_hash_ignores_encoding_noise(ep_text):
    text = ep_text(1)
    base = content_hash(normalize_text(text))
    crlf_bom = (chr(0xFEFF) + text.replace("\n", "\r\n")).encode("utf-8")
    trailing = "\n".join(line + "   " for line in text.split("\n")) + "\n\n"
    assert content_hash(normalize_text(decode_bytes(crlf_bom))) == base
    assert content_hash(normalize_text(trailing)) == base
    assert content_hash(normalize_text(text.replace("Gerald", "Gerard", 1))) != base


def test_hash_is_deterministic(ep_text):
    text = ep_text(2)
    assert content_hash(normalize_text(text)) == content_hash(normalize_text(text))


@pytest.mark.parametrize("text", ["", "hello world", "EPISODE NUMBER: Episode 1\n**CAMERA:**\nno timestamp here\n"])
def test_rejects_non_screenplays(text):
    with pytest.raises(ScreenplayError):
        parse_screenplay(text)
