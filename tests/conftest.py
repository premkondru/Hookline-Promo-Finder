import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402

SHOW_DIR = config.SEED_EPISODES_DIR / "I Married a Broken Soldier. He was a Duke"
EPISODE_FILES = sorted(SHOW_DIR.glob("*.txt"))


def episode_path(number: int) -> Path:
    return next(p for p in EPISODE_FILES if p.name.startswith(f"episode-{number:03d}-"))


@pytest.fixture
def ep_text():
    return lambda number: episode_path(number).read_text(encoding="utf-8")


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(tmp_path, fake=True, start_worker=False, seed=False)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        yield c
