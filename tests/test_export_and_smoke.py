from pathlib import Path
import os
import subprocess
import sys

import pandas as pd

from database.repository import Repository
from models.domain import CandidateProfile, JobDescription, MatchResult
from services.export_service import export_csv, export_excel, results_frame


def test_export_csv_and_excel(tmp_path: Path) -> None:
    candidate = CandidateProfile(id=1, file_name="a.docx", file_hash="hash", candidate_name="Asha")
    job = JobDescription(id=1, title="Developer", description="Build Python services")
    match = MatchResult(
        candidate_id=1,
        job_id=1,
        required_coverage=100,
        preferred_coverage=0,
        experience_coverage=100,
        certification_coverage=100,
        semantic_similarity=50,
        composite_indicator=80,
        explanation="Human review required.",
    )
    frame = results_frame([match], {1: candidate}, {1: job})
    assert b"candidate_name" in export_csv(frame)
    excel = export_excel(frame, pd.DataFrame([{"event": "review"}]))
    assert excel.startswith(b"PK")


def test_repository_smoke_round_trip(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "smoke.sqlite3")
    candidate = repository.add_candidate(CandidateProfile(file_name="a.docx", file_hash="unique"))
    job = repository.add_job(JobDescription(title="Developer", description="Build services"))
    assert repository.get_candidate(candidate.id).file_hash == "unique"
    assert repository.get_job(job.id).title == "Developer"


def test_streamlit_modules_import() -> None:
    from pages import candidates, dashboard, resume_analyzer, settings_page

    assert all(module is not None for module in [dashboard, resume_analyzer, candidates, settings_page])


def test_streamlit_app_smoke(tmp_path: Path) -> None:
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    environment = os.environ.copy()
    environment["RESUMEIQ_DATA_DIR"] = str(tmp_path / "app-data")
    environment["RESUMEIQ_ENVIRONMENT"] = "development"
    environment["RESUMEIQ_DEMO_MODE"] = "false"
    environment["RESUMEIQ_AUTH_REQUIRED"] = "false"
    environment["RESUMEIQ_USE_AZURE_BLOB"] = "false"
    result = subprocess.run(
        [sys.executable, str(app_path)],
        cwd=app_path.parent,
        env=environment,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr
