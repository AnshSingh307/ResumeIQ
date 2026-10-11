from __future__ import annotations

import json
from pathlib import Path

from database.repository import Repository
from models.domain import JobDescription, ScoreWeights
from services.batch_analysis_service import BatchAnalysisService, UploadPayload


def seed_demo_data(repository: Repository, batch: BatchAnalysisService) -> None:
    """Seed only bundled fictional documents into the isolated demo database."""
    if repository.list_candidates():
        return
    root = Path(__file__).parents[1]
    sample_dir = root / "sample_data" / "generated"
    job_path = root / "sample_data" / "sample_jobs.json"
    uploads = [UploadPayload(path.name, path.read_bytes()) for path in sorted(sample_dir.glob("*.docx"))]
    jobs = json.loads(job_path.read_text(encoding="utf-8"))
    if not uploads or not jobs:
        raise RuntimeError("Bundled fictional demo data is missing.")
    first_job = JobDescription.model_validate(jobs[0])
    batch.run_uploads(uploads, first_job, ScoreWeights())
