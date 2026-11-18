"""Per-job files under DATA_DIR/jobs/{job_id}/ (layout documented in core/pipeline.py)."""
import os
import shutil
from uuid import UUID

import config

INPUT_FILE = "input.dcm"


def jobs_root() -> str:
    return os.path.join(config.DATA_DIR, "jobs")


def job_dir(job_id: UUID | str) -> str:
    return os.path.join(jobs_root(), str(UUID(str(job_id))))   # UUID() round-trip: no path tricks via the id


def input_path(job_id) -> str:
    return os.path.join(job_dir(job_id), INPUT_FILE)


def delete_job_files(job_id):
    shutil.rmtree(job_dir(job_id), ignore_errors=True)


def delete_input(job_id):
    try:
        os.remove(input_path(job_id))
    except FileNotFoundError:
        pass
