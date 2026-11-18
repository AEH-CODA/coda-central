"""inference-worker: loads the enabled models once, then claims and runs queued jobs one at a time.

    python worker.py

Queue semantics (plan §4.7):
  * claim:   SELECT ... WHERE status='queued' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
  * liveness: a background thread refreshes the worker row and the running job's heartbeat_at
  * crash:   'running' jobs whose heartbeat is older than STALE_JOB_MINUTES are requeued (failed after MAX_ATTEMPTS)
  * cancel:  the API sets status='cancelled' on a running job; the worker stops at the next progress update
  * TTL:     finished jobs older than RESULT_TTL_DAYS are deleted with their files
  * SIGTERM: finish the current job, then exit
"""
from __future__ import annotations

import logging
import os
import shutil
import signal
import socket
import threading
import time
import traceback
from datetime import timedelta
from uuid import UUID

from sqlalchemy import and_, or_, update

import config
import storage
from core.ingest import IngestError
from core.pipeline import Cancelled, run_pipeline
from db import (CANCELLED, FAILED, QUEUED, RUNNING, SUCCEEDED, InferenceJob, InferenceWorker, SessionLocal,
                init_db, utcnow)

log = logging.getLogger("inference-worker")

PROGRESS_MIN_INTERVAL_S = 1.0
OUTPUT_DIRS = ("bscan", "overlay", "enface")


class JobGone(Cancelled):
    """The job row was cancelled or deleted while running."""


class Worker:
    def __init__(self, adapters: dict, device: str, worker_id: str | None = None):
        self.adapters = adapters          # ref ('id@version') -> ModelAdapter
        self.device = device
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
        self.stop = threading.Event()
        self.current_job: UUID | None = None
        self._last_maintenance = 0.0

    # ---------------------------------------------------------------- liveness
    def beat(self):
        """Refresh this worker's row and the running job's heartbeat."""
        now = utcnow()
        with SessionLocal() as db:
            w = db.get(InferenceWorker, self.worker_id)
            if w is None:
                db.add(InferenceWorker(worker_id=self.worker_id, device=self.device,
                                       models=list(self.adapters), started_at=now, heartbeat_at=now))
            else:
                w.heartbeat_at, w.device, w.models = now, self.device, list(self.adapters)
            if self.current_job is not None:
                db.execute(update(InferenceJob)
                           .where(InferenceJob.id == self.current_job, InferenceJob.status == RUNNING)
                           .values(heartbeat_at=now))
            db.commit()

    def _heartbeat_loop(self):
        while not self.stop.wait(config.HEARTBEAT_SECONDS):
            try:
                self.beat()
            except Exception:
                log.exception("heartbeat failed")

    # ---------------------------------------------------------------- queue
    def claim(self) -> tuple[UUID, str] | None:
        if not self.adapters:
            return None
        pairs = [ref.split("@", 1) for ref in self.adapters]
        with SessionLocal() as db:
            job = (db.query(InferenceJob)
                   .filter(InferenceJob.status == QUEUED,
                           or_(*[and_(InferenceJob.model_id == i, InferenceJob.model_version == v) for i, v in pairs]))
                   .order_by(InferenceJob.created_at)
                   .with_for_update(skip_locked=True)
                   .limit(1)
                   .first())
            if job is None:
                db.rollback()
                return None
            now = utcnow()
            job.status, job.stage, job.progress = RUNNING, "ingest", 0
            job.started_at = job.heartbeat_at = now
            job.worker_id, job.device = self.worker_id, self.device
            job.attempts = (job.attempts or 0) + 1
            job.error_code = job.error_message = None
            db.commit()
            return job.id, job.model_ref

    def _progress_cb(self, job_id: UUID):
        state = {"t": 0.0, "stage": None}

        def cb(stage: str, pct: int):
            now = time.monotonic()
            if stage == state["stage"] and now - state["t"] < PROGRESS_MIN_INTERVAL_S and pct < 100:
                return
            state["t"], state["stage"] = now, stage
            with SessionLocal() as db:
                n = db.execute(update(InferenceJob)
                               .where(InferenceJob.id == job_id, InferenceJob.status == RUNNING,
                                      InferenceJob.worker_id == self.worker_id)
                               .values(stage=stage, progress=min(int(pct), 99), heartbeat_at=utcnow())).rowcount
                db.commit()
            if n == 0:
                raise JobGone()
        return cb

    def _finish(self, job_id: UUID, **values) -> bool:
        """Final update, only if the job is still ours and running. Returns False if it was cancelled/deleted."""
        with SessionLocal() as db:
            n = db.execute(update(InferenceJob)
                           .where(InferenceJob.id == job_id, InferenceJob.status == RUNNING,
                                  InferenceJob.worker_id == self.worker_id)
                           .values(finished_at=utcnow(), heartbeat_at=utcnow(), **values)).rowcount
            db.commit()
        return n > 0

    def _lost(self, job_id: UUID):
        """The job is no longer ours. Cancelled or deleted: remove row and files. Otherwise (requeued after a missed
        heartbeat and claimed elsewhere) leave it alone."""
        with SessionLocal() as db:
            job = db.get(InferenceJob, job_id)
            if job is not None and job.status != CANCELLED:
                log.warning("job %s: taken over (status %s, worker %s); dropping our run", job_id, job.status,
                            job.worker_id)
                return
            if job is not None:
                db.delete(job)
                db.commit()
        storage.delete_job_files(job_id)
        log.info("job %s cancelled and removed", job_id)

    def process(self, job_id: UUID, ref: str):
        adapter = self.adapters[ref]
        out_dir = storage.job_dir(job_id)
        t0 = time.time()
        self.current_job = job_id
        finished = False
        log.info("job %s: start (%s on %s)", job_id, ref, self.device)
        try:
            result = run_pipeline(storage.input_path(job_id), adapter, self.device, out_dir,
                                  progress=self._progress_cb(job_id))
            ok = self._finish(job_id, status=SUCCEEDED, stage="done", progress=100, result_json=result,
                              duration_ms=int((time.time() - t0) * 1000))
            if not ok:
                self._lost(job_id)
                return
            finished = True
            log.info("job %s: succeeded in %.1fs, totals %s", job_id, time.time() - t0,
                     result["volumes_nl"]["total"])
        except Cancelled:
            self._lost(job_id)
        except IngestError as e:
            log.info("job %s: rejected (%s)", job_id, e.code)
            finished = self._fail(job_id, e.code, str(e), t0)
        except FileNotFoundError:
            log.exception("job %s: input missing", job_id)
            finished = self._fail(job_id, "input_missing",
                                  "The uploaded file is no longer available; please upload it again.", t0)
        except Exception:
            # full traceback to logs only; the user gets a generic message
            log.error("job %s: failed\n%s", job_id, traceback.format_exc())
            finished = self._fail(job_id, "internal_error", "Processing failed due to an internal error.", t0)
        finally:
            self.current_job = None
            if finished and not config.KEEP_INPUT:
                storage.delete_input(job_id)

    def _fail(self, job_id: UUID, code: str, message: str, t0: float) -> bool:
        if not self._finish(job_id, status=FAILED, error_code=code, error_message=message[:2000],
                            duration_ms=int((time.time() - t0) * 1000)):
            self._lost(job_id)
            return False
        out_dir = storage.job_dir(job_id)
        for d in OUTPUT_DIRS:   # drop partial outputs
            shutil.rmtree(os.path.join(out_dir, d), ignore_errors=True)
        return True

    # ---------------------------------------------------------------- maintenance
    def recover_own_jobs(self):
        """At startup: jobs this worker id left 'running' (container restarted mid-job) go back to the queue."""
        with SessionLocal() as db:
            n = db.execute(update(InferenceJob)
                           .where(InferenceJob.status == RUNNING, InferenceJob.worker_id == self.worker_id)
                           .values(status=QUEUED, stage="queued", progress=0, worker_id=None)).rowcount
            db.commit()
        if n:
            log.warning("requeued %d job(s) interrupted by a restart of this worker", n)

    def maintenance(self):
        now = utcnow()
        stale = now - timedelta(minutes=config.STALE_JOB_MINUTES)
        expired = now - timedelta(days=config.RESULT_TTL_DAYS)
        purge: list[UUID] = []
        with SessionLocal() as db:
            for job in (db.query(InferenceJob)
                        .filter(InferenceJob.status.in_((RUNNING, CANCELLED)), InferenceJob.heartbeat_at < stale)
                        .with_for_update(skip_locked=True).all()):
                if job.status == CANCELLED:
                    purge.append(job.id)
                    db.delete(job)
                elif job.attempts >= config.MAX_ATTEMPTS:
                    log.warning("job %s: worker lost %d times, marking failed", job.id, job.attempts)
                    job.status, job.finished_at = FAILED, now
                    job.error_code = "worker_lost"
                    job.error_message = "Processing was interrupted repeatedly; please try again later."
                else:
                    log.warning("job %s: no heartbeat since %s, requeueing", job.id, job.heartbeat_at)
                    job.status, job.stage, job.progress, job.worker_id = QUEUED, "queued", 0, None
            for job in (db.query(InferenceJob)
                        .filter(InferenceJob.status.in_((SUCCEEDED, FAILED)), InferenceJob.finished_at < expired)
                        .all()):
                purge.append(job.id)
                db.delete(job)
            db.commit()
            known = {str(j) for (j,) in db.query(InferenceJob.id).all()}
        for job_id in purge:
            storage.delete_job_files(job_id)
        if purge:
            log.info("purged %d job(s)", len(purge))
        self._purge_orphans(known)
        self._last_maintenance = time.monotonic()

    def _purge_orphans(self, known: set[str], min_age_s: float = 3600):
        """Directories without a DB row (e.g. an upload that crashed the API mid-request)."""
        root = storage.jobs_root()
        if not os.path.isdir(root):
            return
        cutoff = time.time() - min_age_s
        for name in os.listdir(root):
            path = os.path.join(root, name)
            if _is_uuid(name) and name not in known and os.path.isdir(path) and os.path.getmtime(path) < cutoff:
                storage.delete_job_files(name)

    # ---------------------------------------------------------------- main loop
    def run_once(self) -> bool:
        """Claims and processes one job. Returns True if a job was processed."""
        claimed = self.claim()
        if claimed is None:
            return False
        self.process(*claimed)
        return True

    def run(self):
        self.recover_own_jobs()
        self.beat()
        threading.Thread(target=self._heartbeat_loop, name="heartbeat", daemon=True).start()
        log.info("worker %s ready on %s with %s", self.worker_id, self.device, ", ".join(self.adapters))
        while not self.stop.is_set():
            try:
                if time.monotonic() - self._last_maintenance >= config.MAINTENANCE_SECONDS:
                    self.maintenance()
                if self.run_once():
                    continue
            except Exception:
                log.exception("worker loop error")
            self.stop.wait(config.WORKER_POLL_SECONDS)
        log.info("worker %s stopped", self.worker_id)


def _is_uuid(s: str) -> bool:
    try:
        UUID(s)
        return True
    except ValueError:
        return False


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from core.registry import load_adapters   # imports TensorFlow lazily

    init_db()
    os.makedirs(storage.jobs_root(), exist_ok=True)
    adapters, device = load_adapters(config.MODELS_DIR, config.ENABLED_MODELS,
                                     verify_checksum=config.VERIFY_MODEL_CHECKSUM)
    worker = Worker(adapters, device)

    def on_signal(signum, _frame):
        log.info("signal %d: finishing the current job, then exiting", signum)
        worker.stop.set()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    worker.run()


if __name__ == "__main__":
    main()
