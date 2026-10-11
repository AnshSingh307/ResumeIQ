from __future__ import annotations

import base64
import json
from pathlib import Path

from config.settings import AppConfig
from database.repository import Repository
from models.domain import CandidateProfile, JobDescription, MatchResult
from pages.candidates import filter_candidates
from services.auth_service import decode_client_principal, resolve_access
from services.azure_services import AzureBlobStorageService
from services.batch_analysis_service import BatchAnalysisService, UploadPayload
from services.demo_service import seed_demo_data
from services.matching_service import MatchingService
from services.skill_service import SemanticSimilarityService, SkillService
from services.workflow_service import ResumeWorkflow


def _batch(config: AppConfig) -> tuple[Repository, BatchAnalysisService]:
    config.ensure_directories()
    repository = Repository(config.database_path)
    workflow = ResumeWorkflow(config, repository)
    matcher = MatchingService(SkillService(), SemanticSimilarityService("tfidf"))
    return repository, BatchAnalysisService(repository, workflow, matcher)


def test_easy_auth_principal_and_tenant_validation() -> None:
    principal = {
        "claims": [
            {"typ": "name", "val": "Recruiter One"},
            {"typ": "tid", "val": "tenant-123"},
        ]
    }
    encoded = base64.b64encode(json.dumps(principal).encode()).decode()
    assert decode_client_principal(encoded)["claims"][0]["val"] == "Recruiter One"

    config = AppConfig(auth_required=True, allowed_tenant_id="tenant-123")
    access = resolve_access(config, {"X-MS-CLIENT-PRINCIPAL": encoded, "X-MS-CLIENT-PRINCIPAL-ID": "user-1"})
    assert access.authenticated is True
    assert access.display_name == "Recruiter One"
    assert access.mode == "authenticated_reviewer"

    denied = resolve_access(
        AppConfig(auth_required=True, allowed_tenant_id="another-tenant"),
        {"X-MS-CLIENT-PRINCIPAL": encoded},
    )
    assert denied.authenticated is False
    assert "allowed tenant" in (denied.reason or "")


def test_auth_required_rejects_missing_headers() -> None:
    access = resolve_access(AppConfig(auth_required=True), {})
    assert access.authenticated is False
    assert "identity header" in (access.reason or "")


def test_batch_processes_multiple_docx_files(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    files = sorted((root / "sample_data" / "generated").glob("*.docx"))[:2]
    config = AppConfig(data_dir=tmp_path / "data")
    repository, batch = _batch(config)
    job = JobDescription(
        title="Python Developer",
        description="Build Python services with SQL and Docker.",
        required_skills=["Python", "SQL"],
        preferred_skills=["Docker"],
    )
    outcome = batch.run_uploads([UploadPayload(path.name, path.read_bytes()) for path in files], job)
    assert len(outcome.results) == 2
    assert outcome.errors == []
    assert len(repository.list_candidates()) == 2
    assert len(repository.list_matches(outcome.job.id)) == 2


def test_demo_seed_is_isolated_from_normal_data(tmp_path: Path) -> None:
    normal_dir = tmp_path / "private"
    demo_dir = tmp_path / "fictional-demo"
    config = AppConfig(data_dir=normal_dir, demo_data_dir=demo_dir, demo_mode=True)
    repository, batch = _batch(config)
    seed_demo_data(repository, batch)
    assert repository.database_path.parent == demo_dir
    assert repository.list_candidates()
    assert not (normal_dir / "resumeiq.sqlite3").exists()


def test_candidate_filters_and_sorting() -> None:
    first = CandidateProfile(id=1, file_name="asha.docx", file_hash="one", candidate_name="Asha", skills=["Python"])
    second = CandidateProfile(id=2, file_name="lee.docx", file_hash="two", candidate_name="Lee", skills=["SQL"])
    first_result = MatchResult(
        candidate_id=1,
        job_id=1,
        required_coverage=90,
        preferred_coverage=0,
        experience_coverage=0,
        certification_coverage=0,
        semantic_similarity=20,
        composite_indicator=45,
        explanation="Human review required.",
    )
    second_result = first_result.model_copy(update={"candidate_id": 2, "required_coverage": 40})
    pairs = [(second, second_result), (first, first_result)]
    assert [candidate.candidate_name for candidate, _ in filter_candidates(pairs)] == ["Asha", "Lee"]
    assert [candidate.candidate_name for candidate, _ in filter_candidates(pairs, search="sql")] == ["Lee"]
    assert [candidate.candidate_name for candidate, _ in filter_candidates(pairs, skills={"Python"})] == ["Asha"]
    assert len(filter_candidates(pairs, minimum_coverage=50)) == 1


def test_production_guardrails_and_missing_blob_credentials(monkeypatch) -> None:
    config = AppConfig(
        environment="production",
        data_dir=Path("/home/data"),
        auth_required=True,
        use_azure_blob=True,
    )
    assert config.deployment_errors() == []
    unsafe = AppConfig(environment="production", data_dir=Path("./data"))
    errors = " ".join(unsafe.deployment_errors())
    assert "AUTH_REQUIRED" in errors
    assert "/home" in errors
    assert "AZURE_BLOB" in errors

    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_ACCOUNT_URL", raising=False)
    assert AzureBlobStorageService().status().configured is False
