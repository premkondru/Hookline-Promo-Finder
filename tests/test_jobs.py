from app import jobs
from app.db import Database
from app.ingest import ingest
from app.llm import ProviderError

from .conftest import episode_path


class QuotaProvider:
    name = "quota"

    def generate_json(self, **kwargs):
        raise ProviderError("Daily quota used up.", kind="quota")

    def list_models(self):
        return []

    def close(self):
        pass


def setup(tmp_path, monkeypatch, n=2):
    monkeypatch.setattr(jobs, "make_provider", lambda key, fake=False: QuotaProvider())
    db = Database(tmp_path / "t.db")
    ingest(db, [(episode_path(i).name, episode_path(i).read_bytes()) for i in range(1, n + 1)], "Show")
    db.set_settings({"api_key": "AIzaSyTESTKEY-0123456789abcdef"})
    return db, jobs.Worker(db)


def test_quota_failure_pauses_and_resume_requeues(tmp_path, monkeypatch):
    db, worker = setup(tmp_path, monkeypatch)
    row = db.claim_next_queued()
    worker._run(row["id"], db.get_settings(), worker._generation)
    assert worker.paused_reason == "Daily quota used up."
    assert db.get_episode(row["id"])["status"] == "failed"
    worker.wake(resume=True)  # e.g. the user saved a new key
    assert worker.paused_reason is None
    assert db.get_episode(row["id"])["status"] == "queued"


def test_stale_job_does_not_re_pause_after_settings_change(tmp_path, monkeypatch):
    db, worker = setup(tmp_path, monkeypatch)
    row = db.claim_next_queued()
    started_under = worker._generation
    worker.wake(resume=True)  # settings changed while the job was still running
    worker._run(row["id"], db.get_settings(), started_under)
    assert worker.paused_reason is None
    assert db.get_episode(row["id"])["status"] == "queued"  # retried with the new settings


class OverloadedProvider(QuotaProvider):
    def generate_json(self, **kwargs):
        raise ProviderError("Gemini server error (503 UNAVAILABLE).", kind="server")


def test_transient_failures_requeue_twice_then_fail(tmp_path, monkeypatch):
    db, worker = setup(tmp_path, monkeypatch, n=1)
    monkeypatch.setattr(jobs, "make_provider", lambda key, fake=False: OverloadedProvider())
    statuses = []
    for _ in range(3):
        row = db.claim_next_queued()
        worker._run(row["id"], db.get_settings(), worker._generation)
        statuses.append(db.get_episode(row["id"])["status"])
    assert statuses == ["queued", "queued", "failed"]
    assert worker.paused_reason is None


def test_threads_stop_promptly(tmp_path, monkeypatch):
    db, worker = setup(tmp_path, monkeypatch, n=1)
    db.set_settings({"api_key": None})  # nothing to do: threads just wait
    worker.start()
    worker.stop()
    for thread in worker._threads:
        thread.join(timeout=3)
        assert not thread.is_alive()
