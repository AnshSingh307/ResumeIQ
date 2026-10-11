from __future__ import annotations

from pathlib import Path

from config.settings import AppConfig
from database.repository import Repository
from models.domain import AuditEvent, CandidateProfile, ProcessingStatus
from services.azure_services import AzureBlobStorageService, AzureDocumentIntelligenceService, AzureLanguageService
from services.document_parser import DocumentParseError, DocumentParser
from services.extraction_service import ProfileExtractionService
from services.storage_service import LocalStorageService


class DuplicateResumeError(ValueError):
    def __init__(self, candidate: CandidateProfile):
        self.candidate = candidate
        super().__init__(f"Duplicate of candidate #{candidate.id}: {candidate.file_name}")


class ResumeWorkflow:
    def __init__(self, config: AppConfig, repository: Repository):
        self.config = config
        self.repository = repository
        self.storage = LocalStorageService(config.upload_dir, config.max_file_mb)
        self.parser = DocumentParser()
        self.extractor = ProfileExtractionService()
        self.actor = "local_reviewer"

    def process(self, file_name: str, data: bytes) -> CandidateProfile:
        self.storage.validate(file_name, data)
        digest = self.storage.sha256(data)
        existing = self.repository.find_candidate_by_hash(digest)
        if existing:
            if existing.processing_status == ProcessingStatus.FAILED and existing.id is not None:
                # A corrected parser/OCR configuration must be able to retry an earlier failure.
                self.repository.delete_candidate(existing.id)
            else:
                raise DuplicateResumeError(existing)
        path, digest = self.storage.save(file_name, data)
        try:
            try:
                text = self.parser.extract(path)
            except DocumentParseError:
                if not self.config.use_azure_document_intelligence:
                    raise
                text = AzureDocumentIntelligenceService().extract_text(data)
            candidate = self.extractor.extract(file_name, digest, text)
            if self.config.use_azure_language:
                try:
                    candidate.azure_entities = AzureLanguageService().extract_entities(text)
                except Exception as exc:
                    candidate.parse_warnings.append(f"Azure Language failed; local extraction retained: {exc}")
                    candidate.processing_status = ProcessingStatus.NEEDS_REVIEW
            if self.config.use_azure_blob:
                try:
                    AzureBlobStorageService().upload(path.name, data)
                except Exception as exc:
                    if self.config.is_production:
                        raise RuntimeError(f"Private Azure Blob upload failed: {exc}") from exc
                    # Cloud storage is optional during local development.
                    candidate.parse_warnings.append(f"Azure Blob upload failed; local copy retained: {exc}")
                    candidate.processing_status = ProcessingStatus.NEEDS_REVIEW
            candidate = self.repository.add_candidate(candidate)
            self.repository.add_audit_event(
                AuditEvent(
                    event_type="resume_processed",
                    entity_type="candidate",
                    entity_id=candidate.id,
                    actor=self.actor,
                    details={"status": candidate.processing_status.value},
                )
            )
            return candidate
        except Exception as exc:
            if self.config.is_production:
                self.storage.delete_by_hash(digest)
            failed = CandidateProfile(
                file_name=Path(file_name).name,
                file_hash=digest,
                processing_status=ProcessingStatus.FAILED,
                parse_warnings=[str(exc)],
            )
            self.repository.add_candidate(failed)
            raise

    def delete(self, candidate: CandidateProfile) -> None:
        if candidate.id is None:
            raise ValueError("Cannot delete an unsaved candidate.")
        if self.config.use_azure_blob:
            blob_name = f"{candidate.file_hash[:12]}_{self.storage.safe_name(candidate.file_name)}"
            AzureBlobStorageService().delete(blob_name)
        self.storage.delete_by_hash(candidate.file_hash)
        self.repository.add_audit_event(
            AuditEvent(
                event_type="candidate_deleted",
                entity_type="candidate",
                entity_id=candidate.id,
                actor=self.actor,
                details={},
            )
        )
        self.repository.delete_candidate(candidate.id)
