"""HTTP API. Shapes are documented in docs/SPEC.md section 3."""

from __future__ import annotations

import codecs
import csv
import io
import json
from datetime import UTC, datetime

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel

from . import config, serialize
from .ingest import ingest
from .llm import ProviderError, make_provider
from .screenplay import blocks_from_json
from .timeline import Segment, promo_lines, transcript

router = APIRouter(prefix="/api")


def _db(request: Request):
    return request.app.state.db


def _worker(request: Request):
    return request.app.state.worker


def _fake(request: Request) -> bool:
    return request.app.state.fake


@router.get("/config")
def get_config(request: Request):
    return {
        "dimensions": [{k: d[k] for k in ("key", "label", "question")} for d in config.DIMENSIONS],
        "models": [{k: m[k] for k in ("id", "label", "note")} for m in config.MODELS],
        "limits": {
            "min_sec": config.MIN_PROMO_SEC,
            "max_sec": config.MAX_PROMO_SEC,
            "hook_window_sec": config.HOOK_WINDOW_SEC,
            "max_segments": config.MAX_SEGMENTS,
        },
        "tones": config.TONES,
        "fake_mode": _fake(request),
    }


# settings ---------------------------------------------------------------------------------------------


def _key_hint(key: str) -> str:
    return f"{key[:4]}…{key[-3:]}" if len(key) > 10 else "…"


def _settings_view(request: Request) -> dict:
    s = _db(request).get_settings()
    key = s.get("api_key") or ""
    available = json.loads(s["available_models"]) if s.get("available_models") else None
    if _fake(request):
        status, message, available = "ok", "Fake mode: no key needed, results are simulated.", list(config.MODEL_IDS)
    elif not key:
        status, message = "missing", "Add a Gemini API key to analyze episodes."
    else:
        status, message = s.get("key_status", "unverified"), s.get("key_message", "")
    return {
        "has_api_key": bool(key) or _fake(request),
        "api_key_hint": _key_hint(key) if key else None,
        "key_status": status,
        "key_message": message,
        "picker_model": s.get("picker_model") or config.DEFAULT_MODEL,
        "judge_model": s.get("judge_model") or config.DEFAULT_MODEL,
        "available_models": available,
        "queue_paused": _worker(request).paused_reason,
    }


def _verify_key(key: str, fake: bool) -> tuple[str, str, list[str] | None]:
    provider = None
    try:
        provider = make_provider(key, fake=fake)
        ids = set(provider.list_models())
        available = [m for m in config.MODEL_IDS if m in ids]
        if not available:
            return "ok", "Key works, but none of Hookline's models are listed for it.", []
        return "ok", f"Key works: {len(available)} of {len(config.MODEL_IDS)} models available.", available
    except ProviderError as exc:
        if exc.kind == "auth":
            return "invalid", str(exc), None
        return "unverified", f"Saved, but the key couldn't be verified: {exc}", None
    except Exception as exc:  # never lose the user's key because verification itself broke
        return "unverified", f"Saved, but the key couldn't be verified ({type(exc).__name__}).", None
    finally:
        if provider is not None:
            provider.close()


class SettingsUpdate(BaseModel):
    api_key: str | None = None
    picker_model: str | None = None
    judge_model: str | None = None


@router.get("/settings")
def get_settings(request: Request):
    return _settings_view(request)


@router.put("/settings")
def put_settings(body: SettingsUpdate, request: Request):
    updates: dict[str, str | None] = {}
    for field in ("picker_model", "judge_model"):
        value = getattr(body, field)
        if value is not None:
            if value not in config.MODEL_IDS:
                raise HTTPException(400, f"Unknown model '{value}'.")
            updates[field] = value
    if body.api_key is not None:
        key = body.api_key.strip()
        if not key:
            updates.update(api_key=None, key_status=None, key_message=None, available_models=None)
        else:
            if not 20 <= len(key) <= 200 or any(ch.isspace() for ch in key):
                raise HTTPException(400, "That doesn't look like a Gemini API key.")
            status, message, available = _verify_key(key, _fake(request))
            if status == "invalid":
                raise HTTPException(400, message)
            updates.update(
                api_key=key,
                key_status=status,
                key_message=message,
                available_models=json.dumps(available) if available is not None else None,
            )
    _db(request).set_settings(updates)
    _worker(request).wake(resume=True)
    return _settings_view(request)


# promos -----------------------------------------------------------------------------------------------


@router.get("/shows")
def list_shows(request: Request):
    return {"shows": [dict(r) for r in _db(request).list_shows()]}


@router.get("/promos")
def list_promos(request: Request, show: str | None = None):
    return {"promos": serialize.ranked(_db(request).list_promos(show))}


@router.get("/promos/{promo_id}")
def get_promo(promo_id: int, request: Request):
    db = _db(request)
    row = db.get_promo(promo_id)
    if row is None:
        raise HTTPException(404, "Promo not found.")
    detail = serialize.promo_detail(row, db.get_episode_blocks(row["episode_id"]))
    # Rank, post-first and duplicate flags depend on the other promos; compute them within this show.
    summary = next(s for s in serialize.ranked(db.list_promos(row["show_title"])) if s["id"] == promo_id)
    detail.update(rank=summary["rank"], post_first=summary["post_first"], flags=summary["flags"])
    return detail


@router.delete("/promos/{promo_id}")
def delete_promo(promo_id: int, request: Request):
    db = _db(request)
    row = db.get_promo(promo_id)
    if row is None:
        raise HTTPException(404, "Promo not found.")
    db.delete_episode(row["episode_id"])
    return {"deleted": True, "episode_id": row["episode_id"]}


# episodes / processing tray ---------------------------------------------------------------------------


@router.get("/episodes")
def list_episodes(request: Request):
    db = _db(request)
    rows = db.list_unfinished()
    has_key = _fake(request) or bool(db.get_setting("api_key"))
    return {
        "episodes": [serialize.tray_item(r) for r in rows],
        "waiting_for_key": not has_key and any(r["status"] == "queued" for r in rows),
        "paused_reason": _worker(request).paused_reason,
    }


@router.post("/episodes/{episode_id}/retry")
def retry_episode(episode_id: int, request: Request):
    if not _db(request).retry_episode(episode_id):
        raise HTTPException(409, "Only failed episodes can be retried.")
    _worker(request).wake(resume=True)
    return {"ok": True}


@router.delete("/episodes/{episode_id}")
def delete_episode(episode_id: int, request: Request):
    if not _db(request).delete_episode(episode_id):
        raise HTTPException(404, "Episode not found.")
    return {"deleted": True}


@router.post("/upload")
async def upload(request: Request, files: list[UploadFile] = File(...), show_title: str | None = Form(None)):
    payload = []
    for f in files:
        name = f.filename or "upload"
        limit = config.MAX_ZIP_BYTES if name.lower().endswith(".zip") else config.MAX_TXT_BYTES
        payload.append((name, await f.read(limit + 1)))
    results = await run_in_threadpool(ingest, _db(request), payload, show_title)
    _worker(request).wake()
    return {
        "results": results,
        "added": sum(r["status"] == "added" for r in results),
        "duplicates": sum(r["status"] == "duplicate" for r in results),
        "invalid": sum(r["status"] == "invalid" for r in results),
    }


# export -----------------------------------------------------------------------------------------------


def _segments_text(promo: dict) -> str:
    return " | ".join(f"{s['start']}-{s['end']}" for s in promo["segments"])


def _csv_safe(value) -> str:
    """Stop spreadsheet apps from treating script text as a formula."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def _promo_full_text(db, promo: dict) -> str:
    """Reconstruct the full promo transcript from the episode's blocks and the promo's segments.

    promo_summary strips start_block/end_block from segments, so we re-fetch the raw row to get them.
    """
    import json as _json
    row = db.get_promo(promo["id"])
    if row is None:
        return ""
    blocks_json = db.get_episode_blocks(promo["episode_id"])
    if not blocks_json:
        return ""
    blocks = blocks_from_json(blocks_json)
    segments = [
        Segment(start=s["start_sec"], end=s["end_sec"], start_block=s["start_block"], end_block=s["end_block"])
        for s in _json.loads(row["segments_json"])
    ]
    lines = promo_lines(blocks, segments)
    return transcript(lines, promo["duration_sec"]).replace("\n", " | ")


def _export_csv(promos: list[dict], db) -> str:
    buf = io.StringIO()
    # Quote every cell so a ';' inside text can't start a new (formula) cell in ';'-separated locales.
    writer = csv.writer(buf, quoting=csv.QUOTE_ALL)
    dims = config.DIMENSIONS
    writer.writerow(
        ["rank", "show", "episode", "title", "segments", "duration_sec", "full promo text", "hook", "hook_type",
         "cliffhanger", "open_question", "why", "composite", *[d["label"] for d in dims], "flags"]
    )
    for p in promos:
        writer.writerow(
            [_csv_safe(v) for v in [
                p["rank"], p["show_title"], p["episode_label"], p["title"], _segments_text(p), p["duration_sec"],
                _promo_full_text(db, p),
                p["hook"], p["hook_type"], p["cliffhanger"], p["open_question"], p["why"], p["composite"],
                *[p["scores"].get(d["key"]) for d in dims],
                "; ".join(f"[{f['level']}] {f['message']}" for f in p["flags"]),
            ]]
        )
    return buf.getvalue()


def _md(text) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ")


def _export_md(promos: list[dict], show: str | None) -> str:
    dims = config.DIMENSIONS
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    out = [
        "# Hookline: ranked promos",
        "",
        f"{'Show: ' + show + ' · ' if show else ''}{len(promos)} promos · generated {stamp} · "
        f"composite = mean of {len(dims)} scores (1-10)",
        "",
        "| # | Episode | Title | Segments | Duration | Composite |",
        "|---|---|---|---|---|---|",
    ]
    for p in promos:
        out.append(
            f"| {p['rank']} | {_md(p['episode_label'])} | {_md(p['title'])} | {_md(_segments_text(p))} | "
            f"{p['duration_sec']:.1f}s | {p['composite']:.2f} |"
        )
    for p in promos:
        scores = " · ".join(f"{d['label']} {p['scores'].get(d['key'], '-')}" for d in dims)
        out += [
            "",
            f"## {p['rank']}. {_md(p['episode_label'])}: {_md(p['title'])} ({p['composite']:.2f})",
            "",
            f"- Segments: {_md(_segments_text(p))} ({p['duration_sec']:.1f}s)",
            f"- Hook ({p['hook_type']}): {_md(p['hook'])}",
            f"- Cliffhanger: {_md(p['cliffhanger'])}",
            f"- Open question: {_md(p['open_question'])}",
            f"- Why it works: {_md(p['why'])}",
            f"- Scores: {scores}",
        ]
        if p["flags"]:
            out.append("- Flags: " + "; ".join(f"[{f['level']}] {_md(f['message'])}" for f in p["flags"]))
    return "\n".join(out) + "\n"


@router.get("/export")
def export(request: Request, format: str = "csv", show: str | None = None):
    db = _db(request)
    promos = serialize.ranked(db.list_promos(show))
    if format == "csv":
        # The byte-order mark makes Excel read the file as UTF-8 (quotes, dashes, ellipses).
        content, media, ext = codecs.BOM_UTF8 + _export_csv(promos, db).encode("utf-8"), "text/csv; charset=utf-8", "csv"
    elif format == "md":
        content, media, ext = _export_md(promos, show).encode("utf-8"), "text/markdown; charset=utf-8", "md"
    else:
        raise HTTPException(400, "format must be csv or md.")
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="hookline-promos.{ext}"'},
    )
