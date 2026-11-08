import csv
import io
import json
import zipfile

from .conftest import episode_path


def upload(client, *files, show_title=None):
    data = {"show_title": show_title} if show_title else {}
    return client.post("/api/upload", files=[("files", f) for f in files], data=data).json()


def txt(number: int, transform=lambda b: b):
    path = episode_path(number)
    return (path.name, transform(path.read_bytes()), "text/plain")


def zip_of(numbers, folder="Zip Show"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n in numbers:
            path = episode_path(n)
            z.writestr(f"{folder}/{path.name}", path.read_bytes())
        z.writestr("__MACOSX/._junk.txt", b"junk")
    return ("batch.zip", buf.getvalue(), "application/zip")


def drain(client):
    client.app.state.worker.drain()


def test_config_lists_dimensions(client):
    cfg = client.get("/api/config").json()
    assert [d["key"] for d in cfg["dimensions"]] == ["hook", "cliffhanger", "clarity", "stakes", "momentum", "premise"]
    assert cfg["models"][0]["id"] == "gemini-3.8-flash"
    assert cfg["fake_mode"] is True


def test_upload_dedup_delete_reupload(client):
    first = upload(client, txt(3), show_title="Duke")
    assert first["added"] == 1 and first["results"][0]["status"] == "added"

    again = upload(client, txt(3))
    assert again["duplicates"] == 1
    assert 'Already in the app as Episode 3 of "Duke"' in again["results"][0]["message"]

    crlf = upload(client, txt(3, lambda b: b"\xef\xbb\xbf" + b.replace(b"\n", b"\r\n")))
    assert crlf["duplicates"] == 1

    tray = client.get("/api/episodes").json()
    assert [e["status"] for e in tray["episodes"]] == ["queued"]
    assert tray["waiting_for_key"] is False  # fake mode needs no key

    drain(client)
    promos = client.get("/api/promos").json()["promos"]
    assert len(promos) == 1 and promos[0]["rank"] == 1 and promos[0]["show_title"] == "Duke"
    assert client.get("/api/episodes").json()["episodes"] == []

    detail = client.get(f"/api/promos/{promos[0]['id']}").json()
    assert detail["lines"] and detail["lines"][0]["t_start"] == 0
    assert set(detail["rationales"]) == set(promos[0]["scores"])

    deleted = client.delete(f"/api/promos/{promos[0]['id']}").json()
    assert deleted["deleted"] is True
    assert client.get("/api/promos").json()["promos"] == []
    assert client.get(f"/api/promos/{promos[0]['id']}").status_code == 404

    again = upload(client, txt(3))
    assert again["added"] == 1  # deleting the promo freed the hash


def test_zip_upload_uses_folder_as_show_and_skips_junk(client):
    body = upload(client, zip_of([1, 2]))
    assert body["added"] == 2 and body["invalid"] == 0
    shows = client.get("/api/shows").json()["shows"]
    assert shows == [{"title": "Zip Show", "episodes": 2, "promos": 0}]


def test_duplicate_within_one_upload(client):
    body = upload(client, txt(5), txt(5, lambda b: b.replace(b"\n", b"\r\n")))
    assert [r["status"] for r in body["results"]] == ["added", "duplicate"]


def test_rejects_unsupported_and_non_screenplays(client):
    body = upload(
        client,
        ("notes.pdf", b"%PDF-1.4", "application/pdf"),
        ("random.txt", b"just some notes", "text/plain"),
        ("broken.zip", b"not a zip", "application/zip"),
    )
    assert [r["status"] for r in body["results"]] == ["invalid", "invalid", "invalid"]


def test_failed_episode_retry_and_delete(client):
    upload(client, txt(4))
    db = client.app.state.db
    episode_id = client.get("/api/episodes").json()["episodes"][0]["id"]
    db.claim_next_queued()
    db.mark_failed(episode_id, "Gemini was down")
    tray = client.get("/api/episodes").json()["episodes"]
    assert tray[0]["status"] == "failed" and tray[0]["error"] == "Gemini was down"
    assert client.post(f"/api/episodes/{episode_id}/retry").json() == {"ok": True}
    assert client.post(f"/api/episodes/{episode_id}/retry").status_code == 409  # only failed ones
    assert client.delete(f"/api/episodes/{episode_id}").json() == {"deleted": True}
    assert upload(client, txt(4))["added"] == 1


def test_settings_never_return_the_key(client):
    key = "AIzaSyTESTKEY-0123456789abcdef"
    body = client.put("/api/settings", json={"api_key": key, "picker_model": "gemini-3.6-flash"}).json()
    assert key not in str(body)
    assert body["api_key_hint"] == "AIza…def"
    assert body["picker_model"] == "gemini-3.6-flash" and body["judge_model"] == "gemini-3.8-flash"
    assert client.put("/api/settings", json={"picker_model": "gpt-5"}).status_code == 400
    assert client.put("/api/settings", json={"api_key": "short"}).status_code == 400
    cleared = client.put("/api/settings", json={"api_key": ""}).json()
    assert cleared["api_key_hint"] is None


def test_cross_origin_writes_are_refused(client):
    r = client.put("/api/settings", json={"picker_model": "gemini-3.6-flash"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    ok = client.put("/api/settings", json={"picker_model": "gemini-3.6-flash"}, headers={"Origin": "http://127.0.0.1"})
    assert ok.status_code == 200


def test_foreign_host_header_is_refused(client):
    assert client.get("/api/config", headers={"host": "evil.example"}).status_code == 400


def test_security_headers(client):
    r = client.get("/api/config")
    assert "script-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"


def test_post_first_prefers_early_episodes_and_skips_blocked(client):
    from app.serialize import BLOCKING_FLAG_CODES

    def blocked(p):
        return any(f["level"] == "error" or f["code"] in BLOCKING_FLAG_CODES for f in p["flags"])

    def expected(promos):  # early episodes (1-2 of 6) first, then the best of the rest, all unblocked
        ok = [p for p in promos if not blocked(p)]
        order = [p for p in ok if p["episode_number"] <= 2] + [p for p in ok if p["episode_number"] > 2]
        return {p["id"] for p in order[:3]}

    upload(client, *(txt(n) for n in range(1, 7)))
    drain(client)
    promos = client.get("/api/promos").json()["promos"]
    assert {p["id"] for p in promos if p["post_first"]} == expected(promos)

    target = next(p for p in promos if p["post_first"])
    db = client.app.state.db
    with db.connect() as conn:
        stored = json.loads(conn.execute("SELECT flags_json FROM promos WHERE id = ?", (target["id"],)).fetchone()[0])
        stored.append({"level": "warn", "code": "spoiler", "message": "Shows the ending."})
        conn.execute("UPDATE promos SET flags_json = ? WHERE id = ?", (json.dumps(stored), target["id"]))
    again = client.get("/api/promos").json()["promos"]
    assert {p["id"] for p in again if p["post_first"]} == expected(again)
    assert target["id"] not in {p["id"] for p in again if p["post_first"]}
    assert next(p for p in again if p["id"] == target["id"])["rank"] == target["rank"]  # flags never re-rank

    detail = client.get(f"/api/promos/{target['id']}").json()
    assert "viewer_question" in detail and "cliffhanger_type" in detail
    assert detail["rank"] == target["rank"] and detail["post_first"] is False
    assert any(f["code"] == "spoiler" for f in detail["flags"])


def test_rank_and_post_first_agree_between_list_and_detail_across_shows(client):
    upload(client, txt(1), txt(2), txt(3), show_title="Show A")
    upload(client, txt(4), txt(5), txt(6), show_title="Show B")
    drain(client)
    promos = client.get("/api/promos").json()["promos"]
    for show in ("Show A", "Show B"):
        assert sorted(p["rank"] for p in promos if p["show_title"] == show) == [1, 2, 3]
    for p in promos:
        detail = client.get(f"/api/promos/{p['id']}").json()
        assert (detail["rank"], detail["post_first"]) == (p["rank"], p["post_first"])


def test_corrupt_zip_entry_is_reported_not_a_500(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("Show/episode-001.txt", episode_path(1).read_bytes())
    data = bytearray(buf.getvalue())
    name_len, extra_len = int.from_bytes(data[26:28], "little"), int.from_bytes(data[28:30], "little")
    start = 30 + name_len + extra_len
    data[start + 10:start + 60] = b"\xff" * 50  # garble the compressed stream
    r = client.post("/api/upload", files=[("files", ("bad.zip", bytes(data), "application/zip"))])
    assert r.status_code == 200
    assert r.json()["results"][0]["status"] == "invalid"


def test_key_verification_crash_still_saves_key(client, monkeypatch):
    from app import api

    class Broken:
        def list_models(self):
            raise ValueError("captive portal returned HTML")

        def close(self):
            pass

    monkeypatch.setattr(api, "make_provider", lambda key, fake=False: Broken())
    body = client.put("/api/settings", json={"api_key": "AIzaSyTESTKEY-0123456789abcdef"})
    assert body.status_code == 200
    assert body.json()["api_key_hint"] == "AIza…def"


def test_exports(client):
    upload(client, txt(1), txt(2))
    drain(client)
    db = client.app.state.db
    with db.connect() as conn:
        conn.execute("UPDATE promos SET title = '=HYPERLINK(\"x\")' WHERE id = (SELECT MIN(id) FROM promos)")
    raw = client.get("/api/export?format=csv").content
    assert raw.startswith(b'\xef\xbb\xbf"rank","show"')  # BOM for Excel, every cell quoted
    csv_body = raw.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(csv_body)))
    assert rows[0][:4] == ["rank", "show", "episode", "title"] and len(rows) == 3
    assert any(r[3].startswith("'=") for r in rows[1:])
    md = client.get("/api/export?format=md").text
    assert md.startswith("# Hookline: ranked promos") and "Why it works" in md
    assert client.get("/api/export?format=xml").status_code == 400
