from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from database.repository import Repository
from models.domain import AuditEvent, CandidateProfile, JobDescription, MatchResult, ScoreWeights
from services.matching_service import MatchingService
from services.workflow_service import DuplicateResumeError, ResumeWorkflow


ProgressCallback = Callable[[int, int, str], None]


@dataclass(frozen=True)
class UploadPayload:
    name: str
    data: bytes


@dataclass
class BatchOutcome:
    job: JobDescription
    results: list[tuple[CandidateProfile, MatchResult]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)


class BatchAnalysisService:
    def __init__(
        self,
        repository: Repository,
        workflow: ResumeWorkflow,
        matcher: MatchingService,
        actor: str = "local_reviewer",
    ):
        self.repository = repository
        self.workflow = workflow
        self.matcher = matcher
        self.actor = actor

    def save_job(self, job: JobDescription) -> JobDescription:
        saved = self.repository.update_job(job) if job.id is not None else self.repository.add_job(job)
        self.repository.add_audit_event(
            AuditEvent(
                event_type="job_saved",
                entity_type="job",
                entity_id=saved.id,
                actor=self.actor,
                details={"title": saved.title},
            )
        )
        return saved

    def run_uploads(
        self,
        uploads: list[UploadPayload],
        job: JobDescription,
        weights: ScoreWeights | None = None,
        progress: ProgressCallback | None = None,
    ) -> BatchOutcome:
        saved_job = self.save_job(job)
        outcome = BatchOutcome(saved_job)
        total = len(uploads)
        for index, upload in enumerate(uploads, start=1):
            if progress:
                progress(index - 1, total, f"Processing {upload.name}")
            try:
                candidate = self.workflow.process(upload.name, upload.data)
            except DuplicateResumeError as exc:
                candidate = exc.candidate
                outcome.duplicates.append(upload.name)
            except Exception as exc:
                outcome.errors.append(f"{upload.name}: {exc}")
                continue
            self._match(candidate, saved_job, weights, outcome)
        if progress:
            progress(total, total, "Analysis complete")
        return outcome

    def run_candidates(
        self,
        candidates: list[CandidateProfile],
        job: JobDescription,
        weights: ScoreWeights | None = None,
        progress: ProgressCallback | None = None,
    ) -> BatchOutcome:
        saved_job = self.save_job(job)
        outcome = BatchOutcome(saved_job)
        total = len(candidates)
        for index, candidate in enumerate(candidates, start=1):
            if progress:
                progress(index - 1, total, f"Analyzing {candidate.candidate_name}")
            self._match(candidate, saved_job, weights, outcome)
        if progress:
            progress(total, total, "Analysis complete")
        return outcome

    def _match(
        self,
        candidate: CandidateProfile,
        job: JobDescription,
        weights: ScoreWeights | None,
        outcome: BatchOutcome,
    ) -> None:
        if candidate.id is None or not candidate.raw_text:
            outcome.errors.append(f"{candidate.file_name}: no readable resume text is available.")
            return
        result = self.matcher.analyze(candidate, job, weights)
        result = self.repository.save_match(result)
        self.repository.add_audit_event(
            AuditEvent(
                event_type="analysis_run",
                entity_type="match",
                entity_id=result.id,
                actor=self.actor,
                details={"candidate_id": candidate.id, "job_id": job.id, "indicator": result.composite_indicator},
            )
        )
        outcome.results.append((candidate, result))

