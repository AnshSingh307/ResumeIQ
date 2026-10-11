from __future__ import annotations

from collections import Counter

from database.repository import Repository
from models.domain import (
    AuditEvent,
    JobRequirement,
    QualityCheckResult,
    QualityFinding,
    QualitySeverity,
    QualityStatus,
    RequirementCategory,
    RequirementImportance,
)
from services.auth_service import AccessContext
from services.skill_service import SkillService


VAGUE_TERMS = {
    "good communication": "Replace this with a specific communication task or verifiable requirement.",
    "hard worker": "Describe the responsibility or measurable outcome instead of a personality label.",
    "young and energetic": "Remove age-coded language and describe the job duties objectively.",
    "culture fit": "Replace this with specific, job-related collaboration expectations.",
    "dynamic personality": "Describe the observable responsibility rather than a personality trait.",
}


class JobQualityService:
    def __init__(self, skills: SkillService | None = None):
        self.skills = skills or SkillService()

    def check(
        self,
        title: str,
        description: str,
        requirements: list[JobRequirement],
        *,
        minimum_experience_years: float | None = None,
        actor: str = "local_reviewer",
    ) -> QualityCheckResult:
        findings: list[QualityFinding] = []
        if not title.strip():
            findings.append(self._finding("missing_title", QualitySeverity.BLOCKING, "The job title is missing.", "Add a clear, job-related title."))
        if len(description.split()) < 12:
            findings.append(self._finding("short_description", QualitySeverity.WARNING, "The job description is very short.", "Add responsibilities, scope, and measurable qualifications."))

        active = [item for item in requirements if item.enabled and item.importance != RequirementImportance.EXCLUDED]
        required = [item for item in active if item.importance == RequirementImportance.REQUIRED]
        if not required:
            findings.append(self._finding("no_required_requirements", QualitySeverity.BLOCKING, "No required qualification is configured.", "Mark at least one job-related requirement as required."))

        counts = Counter((item.normalized_value or self.skills.normalize(item.text)) for item in active)
        for normalized, count in counts.items():
            if normalized and count > 1:
                findings.append(self._finding("duplicate_requirement", QualitySeverity.WARNING, f"The requirement '{normalized}' appears {count} times.", "Merge the duplicate rows before analysis.", normalized))

        positions: dict[str, set[RequirementImportance]] = {}
        for item in requirements:
            if not item.enabled:
                continue
            normalized = (item.normalized_value or self.skills.normalize(item.text)).casefold()
            positions.setdefault(normalized, set()).add(item.importance)
        for normalized, importances in positions.items():
            if RequirementImportance.EXCLUDED in importances and len(importances) > 1:
                findings.append(
                    self._finding(
                        "contradictory_requirement",
                        QualitySeverity.BLOCKING,
                        f"The requirement '{normalized}' is both excluded and evaluative.",
                        "Keep one unambiguous row and remove or disable the conflicting row.",
                        normalized,
                    )
                )

        description_folded = description.casefold()
        for phrase, recommendation in VAGUE_TERMS.items():
            if phrase in description_folded:
                severity = (
                    QualitySeverity.BLOCKING
                    if phrase == "young and energetic" or self.skills.is_sensitive_requirement(phrase)
                    else QualitySeverity.WARNING
                )
                findings.append(self._finding("vague_language", severity, f"Potentially vague language was found: '{phrase}'.", recommendation, phrase))

        sensitive_values = {term for term in [description, *[item.text for item in active]] if self.skills.is_sensitive_requirement(term)}
        for value in sensitive_values:
            excerpt = next((term for term in self.skills.sensitive_terms_found(value)), "protected or sensitive criterion")
            findings.append(self._finding("sensitive_criterion", QualitySeverity.BLOCKING, f"A protected or sensitive criterion was detected: '{excerpt}'.", "Remove it from the job description and structured requirements.", excerpt))

        if minimum_experience_years is not None and minimum_experience_years > 15:
            findings.append(self._finding("excessive_experience", QualitySeverity.WARNING, f"The minimum experience requirement is {minimum_experience_years:g} years.", "Confirm that this threshold is necessary and proportionate for the role."))

        described_skills = set(self.skills.extract(description))
        structured_skills = {
            self.skills.normalize(item.text)
            for item in active
            if item.category == RequirementCategory.SKILL
        }
        for skill in sorted(described_skills - structured_skills):
            findings.append(self._finding("unstructured_skill", QualitySeverity.SUGGESTION, f"'{skill}' appears in the description but is not an active structured requirement.", "Add it, or confirm it is contextual rather than evaluative.", skill))
        for skill in sorted(structured_skills - described_skills):
            findings.append(self._finding("requirement_not_in_description", QualitySeverity.WARNING, f"'{skill}' is structured but does not appear in the job description.", "Add it to the description or remove the structured requirement.", skill))

        for item in active:
            if item.category in {RequirementCategory.RESPONSIBILITY, RequirementCategory.OTHER} and item.importance != RequirementImportance.MANUAL:
                findings.append(self._finding("manual_review_recommended", QualitySeverity.SUGGESTION, f"'{item.text}' may not be reliably established from a resume.", "Mark it for manual verification.", item.text))

        status = QualityStatus.BLOCKED if any(item.severity == QualitySeverity.BLOCKING for item in findings) else QualityStatus.REVIEW if any(item.severity == QualitySeverity.WARNING for item in findings) else QualityStatus.READY
        return QualityCheckResult(status=status, findings=findings, actor=actor)

    @staticmethod
    def save_review(
        repository: Repository,
        result: QualityCheckResult,
        job_id: int,
        warnings_acknowledged: bool,
        access: AccessContext,
    ) -> QualityCheckResult:
        if result.status == QualityStatus.BLOCKED:
            raise ValueError("Blocking job-description issues must be resolved before analysis.")
        warning_codes = [item.code for item in result.findings if item.severity == QualitySeverity.WARNING]
        if warning_codes and not warnings_acknowledged:
            raise ValueError("Non-blocking warnings require reviewer acknowledgement.")
        result.job_id = job_id
        result.warnings_acknowledged = bool(warning_codes and warnings_acknowledged)
        result.actor = access.user_id or access.display_name
        saved = repository.add_quality_check(result)
        if warning_codes and warnings_acknowledged:
            repository.add_audit_event(
                AuditEvent(
                    event_type="quality_warnings_acknowledged",
                    entity_type="job",
                    entity_id=job_id,
                    actor=result.actor,
                    details={"finding_codes": ",".join(warning_codes)},
                )
            )
        return saved

    @staticmethod
    def _finding(code: str, severity: QualitySeverity, message: str, recommendation: str, requirement: str | None = None) -> QualityFinding:
        return QualityFinding(code=code, severity=severity, message=message, recommendation=recommendation, requirement=requirement)
