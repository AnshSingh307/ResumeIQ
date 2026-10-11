from pathlib import Path

import pytest

from config.settings import AppConfig
from database.repository import Repository
from services.storage_service import LocalStorageService
from services.workflow_service import DuplicateResumeError, ResumeWorkflow


def test_empty_and_unsupported_files_are_rejected(tmp_path: Path) -> None:
    storage = LocalStorageService(tmp_path)
    with pytest.raises(ValueError, match="empty"):
        storage.validate("resume.pdf", b"")
    with pytest.raises(ValueError, match="Unsupported"):
        storage.validate("resume.txt", b"hello")


def test_duplicate_detection(sample_docx: Path, tmp_path: Path) -> None:
    config = AppConfig(data_dir=tmp_path / "data")
    config.ensure_directories()
    workflow = ResumeWorkflow(config, Repository(config.database_path))
    data = sample_docx.read_bytes()
    first = workflow.process("resume.docx", data)
    assert first.id is not None
    with pytest.raises(DuplicateResumeError):
        workflow.process("renamed.docx", data)


def test_azure_disabled_parser_failure_stays_local(monkeypatch, tmp_path: Path) -> None:
    config = AppConfig(data_dir=tmp_path / "data", use_azure_document_intelligence=False)
    config.ensure_directories()
    repository = Repository(config.database_path)
    workflow = ResumeWorkflow(config, repository)
    called = False

    def azure_call(_data: bytes) -> str:
        nonlocal called
        called = True
        return "should not be called"

    monkeypatch.setattr("services.azure_services.AzureDocumentIntelligenceService.extract_text", azure_call)
    with pytest.raises(Exception):
        workflow.process("broken.pdf", b"%PDF-broken")
    assert called is False
    assert repository.list_candidates()[0].processing_status.value == "failed"

