"""Upload handling: .txt screenplays or .zip archives of them -> queued episodes, de-duplicated by content hash.

Archives are read in memory; nothing is extracted to disk.
"""

from __future__ import annotations

import io
import json
import re
import sqlite3
import zipfile
from pathlib import PurePosixPath

from . import config
from .db import Database
from .screenplay import ScreenplayError, content_hash, decode_bytes, normalize_text, parse_screenplay


def _result(filename: str, status: str, message: str, episode_id: int | None = None) -> dict:
    return {"filename": filename, "status": status, "episode_id": episode_id, "message": message}


def clean_show_title(title: str | None) -> str | None:
    if not title:
        return None
    title = re.sub(r"\s+", " ", title).strip()[:200]
    return title or None


def _duplicate_message(row) -> str:
    message = f'Already in the app as {row["episode_label"]} of "{row["show_title"]}"'
    if row["status"] == "failed":
        message += " (its analysis failed; retry it from the processing tray)"
    elif row["status"] in ("queued", "analyzing"):
        message += " (still being analyzed)"
    return message + "."


def _ingest_text(db: Database, name: str, data: bytes, show: str, seen: dict[str, str]) -> dict:
    if len(data) > config.MAX_TXT_BYTES:
        return _result(name, "invalid", f"File is larger than {config.MAX_TXT_BYTES // (1024 * 1024)} MB.")
    try:
        normalized = normalize_text(decode_bytes(data))
    except UnicodeDecodeError:
        return _result(name, "invalid", "Not a readable text file.")
    digest = content_hash(normalized)
    if digest in seen:
        return _result(name, "duplicate", f"Same screenplay as {seen[digest]} earlier in this upload.")
    existing = db.find_episode_by_hash(digest)
    if existing is not None:
        return _result(name, "duplicate", _duplicate_message(existing), existing["id"])
    try:
        sp = parse_screenplay(normalized, filename=PurePosixPath(name).name)
    except ScreenplayError as exc:
        return _result(name, "invalid", f"Not a screenplay we can read: {exc}")
    label = sp.episode_label or PurePosixPath(name).stem
    try:
        with db.connect() as conn:
            episode_id = db.insert_episode(
                conn,
                content_hash=digest,
                show_title=show,
                episode_number=sp.episode_number,
                episode_label=label,
                source_filename=PurePosixPath(name).name,
                logline=sp.logline,
                continuity_notes=sp.continuity_notes,
                duration_sec=sp.duration,
                raw_text=normalized,
                blocks_json=json.dumps(sp.blocks_json()),
                scenes_json=json.dumps(sp.scenes),
            )
    except sqlite3.IntegrityError:
        existing = db.find_episode_by_hash(digest)
        return _result(name, "duplicate", _duplicate_message(existing) if existing else "Already in the app.")
    seen[digest] = PurePosixPath(name).name
    return _result(name, "added", f"{label} queued for analysis.", episode_id)


def _zip_show_title(names: list[str], zip_name: str) -> str:
    tops = {PurePosixPath(n).parts[0] for n in names if len(PurePosixPath(n).parts) > 1}
    if len(tops) == 1:
        return tops.pop()
    return PurePosixPath(zip_name).stem


def _ingest_zip(db: Database, name: str, data: bytes, show: str | None, seen: dict[str, str]) -> list[dict]:
    if len(data) > config.MAX_ZIP_BYTES:
        return [_result(name, "invalid", f"Archive is larger than {config.MAX_ZIP_BYTES // (1024 * 1024)} MB.")]
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except Exception:  # BadZipFile, but also bad entry-name encodings and other corrupt headers
        return [_result(name, "invalid", "Not a valid .zip archive.")]
    with archive:
        entries = [
            info
            for info in archive.infolist()
            if not info.is_dir()
            and info.filename.lower().endswith(".txt")
            and not any(part.startswith((".", "__MACOSX")) for part in PurePosixPath(info.filename).parts)
        ]
        if not entries:
            return [_result(name, "invalid", "No .txt screenplays inside the archive.")]
        if len(entries) > config.MAX_ZIP_ENTRIES:
            return [_result(name, "invalid", f"Archive has more than {config.MAX_ZIP_ENTRIES} files.")]
        if sum(info.file_size for info in entries) > config.MAX_ZIP_TOTAL_BYTES:
            return [_result(name, "invalid", "Archive expands to more than the allowed size.")]
        show = show or clean_show_title(_zip_show_title([info.filename for info in entries], name)) or config.UNTITLED_SHOW
        results = []
        for info in sorted(entries, key=lambda i: i.filename):
            label = f"{name} > {info.filename}"
            try:
                with archive.open(info) as fh:
                    content = fh.read(config.MAX_TXT_BYTES + 1)
            except Exception as exc:  # corrupt stream (zlib.error, EOFError), encrypted entry, ...
                results.append(_result(label, "invalid", f"Couldn't read this entry ({type(exc).__name__})."))
                continue
            results.append(_ingest_text(db, label, content, show, seen))
        return results


def ingest(db: Database, files: list[tuple[str, bytes]], show_title: str | None = None) -> list[dict]:
    show_title = clean_show_title(show_title)
    seen: dict[str, str] = {}
    results = []
    for name, data in files:
        lower = name.lower()
        if lower.endswith(".zip"):
            results.extend(_ingest_zip(db, name, data, show_title, seen))
        elif lower.endswith(".txt"):
            results.append(_ingest_text(db, name, data, show_title or config.UNTITLED_SHOW, seen))
        else:
            results.append(_result(name, "invalid", "Only .txt screenplays or .zip archives of them are supported."))
    return results
