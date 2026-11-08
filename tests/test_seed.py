import json

from app import seed
from app.db import Database
from app.jobs import Worker


def test_first_run_queues_bundled_episodes_without_analyzing_them(tmp_path):
    db = Database(tmp_path / "a.db")
    seed.seed_if_needed(db)
    assert db.count_status("queued") == 50
    assert db.list_promos() == []  # nothing is pre-analyzed
    seed.seed_if_needed(db)  # idempotent
    assert db.count_status("queued") == 50
    assert [dict(s) for s in db.list_shows()] == [
        {"title": "I Married a Broken Soldier. He was a Duke", "episodes": 50, "promos": 0}
    ]


def test_deleted_bundled_episodes_are_not_re_imported(tmp_path):
    db = Database(tmp_path / "a.db")
    seed.seed_if_needed(db)
    db.delete_episode(db.claim_next_queued()["id"])
    seed.seed_if_needed(db)
    assert db.count_status("queued") == 49


def test_export_snapshots_a_finished_run(tmp_path):
    db = Database(tmp_path / "a.db")
    seed.seed_if_needed(db)
    Worker(db, fake=True).drain()
    out = tmp_path / "run.json"
    assert seed.export_promos(db, out) == 50
    records = json.loads(out.read_text(encoding="utf-8"))
    assert {"content_hash", "show_title", "episode_label", "promo"} <= set(records[0])
    assert {"segments_json", "scores_json", "composite"} <= set(records[0]["promo"])
