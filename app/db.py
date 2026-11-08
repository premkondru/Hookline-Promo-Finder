"""SQLite storage: settings, episodes (keyed by content hash) and their promos."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS episodes (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash     TEXT NOT NULL UNIQUE,
    show_title       TEXT NOT NULL,
    episode_number   INTEGER,
    episode_label    TEXT NOT NULL,
    source_filename  TEXT,
    logline          TEXT,
    continuity_notes TEXT,
    duration_sec     REAL NOT NULL,
    raw_text         TEXT NOT NULL,
    blocks_json      TEXT NOT NULL,
    scenes_json      TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'queued'
                     CHECK (status IN ('queued', 'analyzing', 'done', 'failed')),
    error            TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS episodes_status ON episodes (status);

CREATE TABLE IF NOT EXISTS promos (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id        INTEGER NOT NULL UNIQUE REFERENCES episodes (id) ON DELETE CASCADE,
    title             TEXT NOT NULL,
    hook              TEXT NOT NULL,
    hook_type         TEXT NOT NULL,
    cliffhanger       TEXT NOT NULL,
    cliffhanger_type  TEXT NOT NULL DEFAULT 'other',
    open_question     TEXT NOT NULL,
    viewer_question   TEXT NOT NULL DEFAULT '',
    why               TEXT NOT NULL,
    segments_json     TEXT NOT NULL,
    duration_sec      REAL NOT NULL,
    scores_json       TEXT NOT NULL,
    composite         REAL NOT NULL,
    flags_json        TEXT NOT NULL,
    confusions_json   TEXT NOT NULL,
    tone              TEXT NOT NULL,
    hook_block        INTEGER NOT NULL,
    cliffhanger_block INTEGER NOT NULL,
    candidates_json   TEXT NOT NULL,
    picker_model      TEXT NOT NULL,
    judge_model       TEXT NOT NULL,
    meta_json         TEXT NOT NULL,
    created_at        TEXT NOT NULL
);
"""

# Columns added after the first schema; older databases get them on startup.
_ADDED_PROMO_COLUMNS = {
    "cliffhanger_type": "TEXT NOT NULL DEFAULT 'other'",
    "viewer_question": "TEXT NOT NULL DEFAULT ''",
}

PROMO_COLUMNS = [
    "title", "hook", "hook_type", "cliffhanger", "cliffhanger_type", "open_question", "viewer_question", "why",
    "segments_json", "duration_sec",
    "scores_json", "composite", "flags_json", "confusions_json", "tone", "hook_block", "cliffhanger_block",
    "candidates_json", "picker_model", "judge_model", "meta_json",
]


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)
            existing = {row["name"] for row in conn.execute("PRAGMA table_info(promos)")}
            for column, ddl in _ADDED_PROMO_COLUMNS.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE promos ADD COLUMN {column} {ddl}")

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=NORMAL")  # safe with WAL; avoids an fsync per commit
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    # settings -----------------------------------------------------------------------------------------

    def get_settings(self) -> dict[str, str]:
        with self.connect() as conn:
            return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_settings(self, values: dict[str, str | None]) -> None:
        with self.connect() as conn:
            for key, value in values.items():
                if value is None:
                    conn.execute("DELETE FROM settings WHERE key = ?", (key,))
                else:
                    conn.execute(
                        "INSERT INTO settings (key, value) VALUES (?, ?) "
                        "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                        (key, value),
                    )

    # episodes -----------------------------------------------------------------------------------------

    def find_episode_by_hash(self, content_hash: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM episodes WHERE content_hash = ?", (content_hash,)).fetchone()

    def insert_episode(self, conn: sqlite3.Connection, **fields) -> int:
        stamp = now()
        fields = {**fields, "status": fields.get("status", "queued"), "created_at": stamp, "updated_at": stamp}
        columns = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        cur = conn.execute(f"INSERT INTO episodes ({columns}) VALUES ({marks})", list(fields.values()))
        return int(cur.lastrowid)

    def get_episode(self, episode_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,)).fetchone()

    def list_unfinished(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT id, show_title, episode_number, episode_label, status, error, source_filename, created_at "
                "FROM episodes WHERE status != 'done' ORDER BY show_title, episode_number, id"
            ).fetchall()

    def count_status(self, status: str) -> int:
        with self.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM episodes WHERE status = ?", (status,)).fetchone()[0]

    def claim_next_queued(self) -> sqlite3.Row | None:
        with self.connect() as conn:
            rows = conn.execute(
                "UPDATE episodes SET status = 'analyzing', error = NULL, updated_at = ? "
                "WHERE id = (SELECT id FROM episodes WHERE status = 'queued' "
                "            ORDER BY show_title, episode_number, id LIMIT 1) "
                "RETURNING *",
                (now(),),
            ).fetchall()
        return rows[0] if rows else None

    def requeue_interrupted(self) -> int:
        with self.connect() as conn:
            return conn.execute(
                "UPDATE episodes SET status = 'queued', updated_at = ? WHERE status = 'analyzing'", (now(),)
            ).rowcount

    def mark_failed(self, episode_id: int, error: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE episodes SET status = 'failed', error = ?, updated_at = ? WHERE id = ?",
                (error[:2000], now(), episode_id),
            )

    def requeue(self, episode_id: int) -> bool:
        with self.connect() as conn:
            return conn.execute(
                "UPDATE episodes SET status = 'queued', error = NULL, updated_at = ? "
                "WHERE id = ? AND status IN ('analyzing', 'failed')",
                (now(), episode_id),
            ).rowcount > 0

    def retry_episode(self, episode_id: int) -> bool:
        with self.connect() as conn:
            return conn.execute(
                "UPDATE episodes SET status = 'queued', error = NULL, updated_at = ? "
                "WHERE id = ? AND status = 'failed'",
                (now(), episode_id),
            ).rowcount > 0

    def delete_episode(self, episode_id: int) -> bool:
        """Deletes the episode, its hash and (via cascade) its promo, so the file can be uploaded again."""
        with self.connect() as conn:
            return conn.execute("DELETE FROM episodes WHERE id = ?", (episode_id,)).rowcount > 0

    # promos -------------------------------------------------------------------------------------------

    def save_promo(self, episode_id: int, values: dict) -> bool:
        """Store the promo and mark the episode done. False if the episode was deleted meanwhile."""
        with self.connect() as conn:
            if conn.execute("SELECT 1 FROM episodes WHERE id = ?", (episode_id,)).fetchone() is None:
                return False
            conn.execute("DELETE FROM promos WHERE episode_id = ?", (episode_id,))
            row = {k: values[k] for k in PROMO_COLUMNS}
            row.update(episode_id=episode_id, created_at=values.get("created_at") or now())
            columns = ", ".join(row)
            marks = ", ".join("?" for _ in row)
            conn.execute(f"INSERT INTO promos ({columns}) VALUES ({marks})", list(row.values()))
            conn.execute(
                "UPDATE episodes SET status = 'done', error = NULL, updated_at = ? WHERE id = ?", (now(), episode_id)
            )
            return True

    _PROMO_SELECT = (
        "SELECT p.*, e.show_title, e.episode_number, e.episode_label, e.source_filename, e.logline, "
        "e.duration_sec AS episode_duration_sec, e.content_hash FROM promos p JOIN episodes e ON e.id = p.episode_id"
    )

    def list_promos(self, show: str | None = None) -> list[sqlite3.Row]:
        with self.connect() as conn:
            if show:
                return conn.execute(
                    self._PROMO_SELECT + " WHERE e.show_title = ? ORDER BY p.composite DESC, e.episode_number",
                    (show,),
                ).fetchall()
            return conn.execute(self._PROMO_SELECT + " ORDER BY p.composite DESC, e.episode_number").fetchall()

    def get_promo(self, promo_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(self._PROMO_SELECT + " WHERE p.id = ?", (promo_id,)).fetchone()

    def get_episode_blocks(self, episode_id: int) -> list[dict]:
        with self.connect() as conn:
            row = conn.execute("SELECT blocks_json FROM episodes WHERE id = ?", (episode_id,)).fetchone()
        return json.loads(row["blocks_json"]) if row else []

    def list_shows(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT e.show_title AS title, COUNT(*) AS episodes, COUNT(p.id) AS promos "
                "FROM episodes e LEFT JOIN promos p ON p.episode_id = e.id "
                "GROUP BY e.show_title ORDER BY e.show_title"
            ).fetchall()
