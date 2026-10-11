from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class RequirementStatus(StrEnum):
    MATCHED = "matched"
    NOT_FOUND = "not_found"
    UNCERTAIN = "uncertain"
    MANUAL_VERIFY = "manual_verification"


class RequirementCategory(StrEnum):
    SKILL = "skill"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    CERTIFICATION = "certification"
    RESPONSIBILITY = "responsibility"
    OTHER = "other"


class RequirementImportance(StrEnum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    MANUAL = "manual_verification"
    EXCLUDED = "excluded"


class RequirementEvaluationMethod(StrEnum):
    RESUME_EVIDENCE = "resume_evidence"
    NUMERIC_EXPERIENCE = "numeric_experience"
    CERTIFICATION_EVIDENCE = "certification_evidence"
    EDUCATION_EVIDENCE = "education_evidence"
    HUMAN_ONLY = "human_verification_only"


class QualitySeverity(StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"
    SUGGESTION = "suggestion"


class QualityStatus(StrEnum):
    READY = "ready"
    REVIEW = "review_recommended"
    BLOCKED = "blocked"


class JobRequirement(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    normalized_value: str = ""
    category: RequirementCategory = RequirementCategory.SKILL
    importance: RequirementImportance = RequirementImportance.REQUIRED
    evaluation_method: RequirementEvaluationMethod = RequirementEvaluationMethod.RESUME_EVIDENCE
    notes: str = Field(default="", max_length=1000)
    enabled: bool = True
    source: Literal["suggested", "manual", "legacy"] = "manual"
    sort_order: int = Field(default=0, ge=0)

    @field_validator("text", "normalized_value", "notes")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return " ".join(value.strip().split())


class JobRequirementVersion(BaseModel):
    id: int | None = None
    job_id: int
    version_number: int = Field(ge=1)
    requirements: list[JobRequirement] = Field(default_factory=list)
    change_summary: str = "Requirement set saved"
    actor: str = "local_reviewer"
    created_at: datetime = Field(default_factory=utc_now)


class QualityFinding(BaseModel):
    code: str
    severity: QualitySeverity
    message: str
    recommendation: str
    requirement: str | None = None


class QualityCheckResult(BaseModel):
    id: int | None = None
    job_id: int | None = None
    status: QualityStatus
    findings: list[QualityFinding] = Field(default_factory=list)
    warnings_acknowledged: bool = False
    actor: str = "local_reviewer"
    created_at: datetime = Field(default_factory=utc_now)


class CandidateCorrection(BaseModel):
    id: int | None = None
    candidate_id: int
    field_name: str
    original_value: Any = None
    corrected_value: Any = None
    reason: str = Field(min_length=3, max_length=1000)
    actor: str = "local_reviewer"
    active: bool = True
    created_at: datetime = Field(default_factory=utc_now)
    reverted_at: datetime | None = None
    reverted_by: str | None = None


class EvidenceSnippet(BaseModel):
    qualification: str
    snippet: str
    source: str = "resume"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class EmploymentEntry(BaseModel):
    title: str = "Unspecified role"
    organization: str | None = None
    period: str | None = None
    evidence: str


class CandidateProfile(BaseModel):
    id: int | None = None
    file_name: str
    file_hash: str
    candidate_name: str = "Name requires verification"
    email: str | None = None
    phone: str | None = None
    skills: list[str] = Field(default_factory=list)
    skill_evidence: dict[str, list[EvidenceSnippet]] = Field(default_factory=dict)
    education: list[str] = Field(default_factory=list)
    employment_history: list[EmploymentEntry] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    azure_entities: list[dict[str, str | float]] = Field(default_factory=list)
    years_experience: float | None = Field(default=None, ge=0)
    raw_text: str = ""
    parse_warnings: list[str] = Field(default_factory=list)
    reviewer_comments: list[str] = Field(default_factory=list)
    processing_status: ProcessingStatus = ProcessingStatus.PENDING
    created_at: datetime = Field(default_factory=utc_now)


class JobDescription(BaseModel):
    id: int | None = None
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    minimum_experience_years: float | None = Field(default=None, ge=0, le=80)
    education_requirements: str | None = None
    certification_requirements: list[str] = Field(default_factory=list)
    requirements: list[JobRequirement] = Field(default_factory=list)
    requirement_version_id: int | None = None
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("required_skills", "preferred_skills", "certification_requirements")
    @classmethod
    def clean_list(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            item = " ".join(value.strip().split())
            if item and item.lower() not in {existing.lower() for existing in cleaned}:
                cleaned.append(item)
        return cleaned


class ScoreWeights(BaseModel):
    required_skills: float = Field(default=0.5, ge=0)
    preferred_skills: float = Field(default=0.2, ge=0)
    experience: float = Field(default=0.2, ge=0)
    certifications: float = Field(default=0.1, ge=0)

    def normalized(self) -> dict[str, float]:
        values = self.model_dump()
        total = sum(values.values())
        if total <= 0:
            return {key: 0.0 for key in values}
        return {key: value / total for key, value in values.items()}


class RequirementAssessment(BaseModel):
    requirement: str
    category: Literal[
        "required_skill",
        "preferred_skill",
        "experience",
        "certification",
        "education",
        "responsibility",
        "other",
    ]
    status: RequirementStatus
    evidence: list[EvidenceSnippet] = Field(default_factory=list)
    explanation: str


class MatchResult(BaseModel):
    id: int | None = None
    candidate_id: int
    job_id: int
    required_coverage: float = Field(ge=0, le=100)
    preferred_coverage: float = Field(ge=0, le=100)
    experience_coverage: float = Field(ge=0, le=100)
    certification_coverage: float = Field(ge=0, le=100)
    semantic_similarity: float = Field(ge=0, le=100)
    composite_indicator: float = Field(ge=0, le=100)
    assessments: list[RequirementAssessment] = Field(default_factory=list)
    explanation: str
    requirement_version_id: int | None = None
    created_at: datetime = Field(default_factory=utc_now)


class AuditEvent(BaseModel):
    id: int | None = None
    event_type: str
    entity_type: str
    entity_id: int | None = None
    actor: str = "local_reviewer"
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
