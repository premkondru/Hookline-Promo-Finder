"""Background analysis queue: daemon threads claim queued episodes from the DB and run the pipeline.

The threads are daemons so shutting the app down never waits on a slow Gemini call. An analysis cut short that
way leaves its episode in 'analyzing', and start() re-queues it next time.
"""

from __future__ import annotations

import logging
import threading

from . import config
from .db import Database
from .llm import ProviderError, make_provider
from .pipeline import PipelineError, analyze
from .serialize import episode_input, promo_values

log = logging.getLogger(__name__)

# Server/network failures (e.g. a 503 "model overloaded" that outlasts the provider's own retries) put the
# episode back in the queue this many times before it's marked failed.
_TRANSIENT_REQUEUES = 2


class Worker:
    def __init__(self, db: Database, fake: bool = False, concurrency: int = config.WORKER_CONCURRENCY):
        self.db = db
        self.fake = fake
        self.concurrency = concurrency
        self.paused_reason: str | None = None
        self._cond = threading.Condition()
        self._stopping = False
        # Bumped whenever settings change; a job that fails under older settings must not pause the queue.
        self._generation = 0
        self._paused_failures: set[int] = set()
        self._transient_retries: dict[int, int] = {}
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        requeued = self.db.requeue_interrupted()
        if requeued:
            log.info("Re-queued %d episodes interrupted by the last shutdown", requeued)
        for n in range(self.concurrency):
            thread = threading.Thread(target=self._loop, name=f"hookline-analyze-{n}", daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        with self._cond:
            self._stopping = True
            self._cond.notify_all()

    def wake(self, resume: bool = False) -> None:
        """Nudge the queue. resume=True (settings saved, or a retry) also lifts a pause caused by a bad key,
        an unavailable model or an exhausted quota, and re-queues the episodes that pause failed."""
        with self._cond:
            if resume:
                self._generation += 1
                self.paused_reason = None
                for episode_id in self._paused_failures:
                    self.db.retry_episode(episode_id)
                self._paused_failures.clear()
            self._cond.notify_all()

    def drain(self) -> None:
        """Process every queued episode synchronously, in this thread (tests and command-line runs)."""
        settings = self.db.get_settings()
        while (row := self.db.claim_next_queued()) is not None:
            self._run(row["id"], settings, self._generation)

    def _loop(self) -> None:
        while True:
            with self._cond:
                if self._stopping:
                    return
                generation = self._generation
                paused = self.paused_reason is not None
            job = settings = None
            if not paused:
                try:
                    settings = self.db.get_settings()
                    if self.fake or settings.get("api_key"):
                        job = self.db.claim_next_queued()
                except Exception:
                    log.exception("Worker couldn't read the queue")
            if job is not None:
                self._run(job["id"], settings, generation)
                continue
            with self._cond:
                if not self._stopping:
                    self._cond.wait(timeout=2.0)

    def _run(self, episode_id: int, settings: dict, generation: int) -> None:
        provider = None
        try:
            row = self.db.get_episode(episode_id)
            if row is None:
                return
            picker_model = settings.get("picker_model") or config.DEFAULT_MODEL
            judge_model = settings.get("judge_model") or config.DEFAULT_MODEL
            provider = make_provider(settings.get("api_key"), fake=self.fake)
            log.info("Analyzing %s (episode id %d) with %s / %s", row["episode_label"], episode_id, picker_model, judge_model)
            result = analyze(episode_input(row), provider, picker_model, judge_model)
            if not self.db.save_promo(episode_id, promo_values(result)):
                log.info("Episode %d was deleted during analysis; result discarded", episode_id)
        except ProviderError as exc:
            if exc.kind in ("server", "network"):
                with self._cond:
                    retries = self._transient_retries.get(episode_id, 0)
                    if retries < _TRANSIENT_REQUEUES:
                        self._transient_retries[episode_id] = retries + 1
                if retries < _TRANSIENT_REQUEUES:
                    log.warning("%s on episode %d; re-queued (%d/%d)", exc, episode_id, retries + 1, _TRANSIENT_REQUEUES)
                    self.db.requeue(episode_id)
                    return
            if not exc.pauses_queue:
                self.db.mark_failed(episode_id, str(exc))
                return
            with self._cond:
                if generation == self._generation:
                    self.paused_reason = str(exc)
                    self._paused_failures.add(episode_id)
                    self.db.mark_failed(episode_id, str(exc))
                    log.warning("Queue paused: %s", exc)
                else:
                    # Settings changed while this ran; try it again with the new ones.
                    self.db.requeue(episode_id)
                self._cond.notify_all()
        except PipelineError as exc:
            self.db.mark_failed(episode_id, str(exc))
        except Exception as exc:
            log.exception("Unexpected error analyzing episode %d", episode_id)
            self.db.mark_failed(episode_id, f"Unexpected error: {type(exc).__name__}: {exc}")
        finally:
            if provider is not None:
                provider.close()
