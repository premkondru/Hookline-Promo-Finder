"""Bundled data: the show's episodes ship in seed/episodes/<show>/ and are imported, queued, on first run.
Nothing is pre-analyzed: analysis starts once a Gemini key is saved in Settings.

A finished run can be snapshotted for evaluation (eval/compare.py --snapshot) with:
    python -m app.seed export [--data-dir data] [--out eval/run_promos.json]
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from . import config
from .db import PROMO_COLUMNS, Database
from .ingest import ingest

log = logging.getLogger(__name__)


def seed_if_needed(db: Database) -> None:
    if db.get_setting("seeded") == "1":
        return
    if config.SEED_EPISODES_DIR.is_dir():
        for show_dir in sorted(p for p in config.SEED_EPISODES_DIR.iterdir() if p.is_dir()):
            files = [(p.name, p.read_bytes()) for p in sorted(show_dir.glob("*.txt"))]
            results = ingest(db, files, show_dir.name)
            log.info("Queued %d bundled episodes of %s", sum(r["status"] == "added" for r in results), show_dir.name)
    db.set_settings({"seeded": "1"})


def export_promos(db: Database, path: Path) -> int:
    records = []
    for row in db.list_promos():
        promo = {k: row[k] for k in PROMO_COLUMNS}
        promo["created_at"] = row["created_at"]
        records.append(
            {
                "content_hash": row["content_hash"],
                "show_title": row["show_title"],
                "episode_label": row["episode_label"],
                "promo": promo,
            }
        )
    records.sort(key=lambda r: (r["show_title"], r["episode_label"]))
    path.write_text(json.dumps(records, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(description="Snapshot analyzed promos for evaluation.")
    parser.add_argument("command", choices=["export"])
    parser.add_argument("--data-dir", type=Path, default=config.DEFAULT_DATA_DIR)
    parser.add_argument("--out", type=Path, default=config.RUN_SNAPSHOT_FILE)
    args = parser.parse_args()
    db = Database(args.data_dir / "hookline.db")
    count = export_promos(db, args.out)
    print(f"Wrote {count} promos to {args.out}")


if __name__ == "__main__":
    main()
