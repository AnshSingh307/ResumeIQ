from __future__ import annotations

import json

from database.repository import Repository
from models.domain import (
    AuditEvent,
    JobDescription,
    JobRequirement,
    JobRequirementVersion,
    RequirementCategory,
    RequirementEvaluationMethod,
    RequirementImportance,
)
from services.skill_service import SkillService


class RequirementService:
    def __init__(self, skills: SkillService | None = None):
        self.skills = skills or SkillService()

    def from_job(self, job: JobDescription | None) -> list[JobRequirement]:
        if job is None:
            return []
        if job.requirements:
            return [item.model_copy(deep=True) for item in job.requirements]
        rows: list[JobRequirement] = []
        for value in job.required_skills:
            rows.append(self._skill(value, RequirementImportance.REQUIRED, "legacy", len(rows)))
        for value in job.preferred_skills:
            rows.append(self._skill(value, RequirementImportance.PREFERRED, "legacy", len(rows)))
        if job.minimum_experience_years is not None:
            rows.append(
                JobRequirement(
                    text=f"{job.minimum_experience_years:g}+ years relevant experience",
                    normalized_value=f"{job.minimum_experience_years:g} years experience",
                    category=RequirementCategory.EXPERIENCE,
                    importance=RequirementImportance.REQUIRED,
                    evaluation_method=RequirementEvaluationMethod.NUMERIC_EXPERIENCE,
                    notes="Uses the explicit minimum-experience field.",
                    source="legacy",
                    sort_order=len(rows),
                )
            )
        if job.education_requirements:
            rows.append(
                JobRequirement(
                    text=job.education_requirements,
                    normalized_value=self.skills.normalize(job.education_requirements),
                    category=RequirementCategory.EDUCATION,
                    importance=RequirementImportance.MANUAL,
                    evaluation_method=RequirementEvaluationMethod.HUMAN_ONLY,
                    source="legacy",
                    sort_order=len(rows),
                )
            )
        for value in job.certification_requirements:
            rows.append(
                JobRequirement(
                    text=value,
                    normalized_value=self.skills.normalize(value),
                    category=RequirementCategory.CERTIFICATION,
                    importance=RequirementImportance.REQUIRED,
                    evaluation_method=RequirementEvaluationMethod.CERTIFICATION_EVIDENCE,
                    source="legacy",
                    sort_order=len(rows),
                )
            )
        return rows

    def suggest(
        self,
        description: str,
        required_values: list[str],
        preferred_values: list[str],
        existing: list[JobRequirement] | None = None,
    ) -> list[JobRequirement]:
        rows = [item.model_copy(deep=True) for item in (existing or [])]
        known = {(item.normalized_value or self.skills.normalize(item.text)).casefold() for item in rows}
        for value, importance, source in [
            *[(item, RequirementImportance.REQUIRED, "manual") for item in required_values],
            *[(item, RequirementImportance.PREFERRED, "manual") for item in preferred_values],
            *[(item, RequirementImportance.PREFERRED, "suggested") for item in self.skills.extract(description)],
        ]:
            normalized = self.skills.normalize(value)
            if not normalized or normalized.casefold() in known:
                continue
            rows.append(self._skill(value, importance, source, len(rows)))
            known.add(normalized.casefold())
        return rows

    def validate(self, requirements: list[JobRequirement]) -> list[str]:
        errors: list[str] = []
        active = [item for item in requirements if item.enabled and item.importance != RequirementImportance.EXCLUDED]
        if not any(item.importance == RequirementImportance.REQUIRED for item in active):
            errors.append("At least one active requirement must be marked required.")
        seen: set[str] = set()
        for item in active:
            normalized = (item.normalized_value or self.skills.normalize(item.text)).casefold()
            if normalized in seen:
                errors.append(f"Duplicate active requirement: {item.text}")
            seen.add(normalized)
            if self.skills.is_sensitive_requirement(item.text):
                errors.append(f"Protected or sensitive requirement cannot be enabled: {item.text}")
        return errors

    def merge_duplicates(self, requirements: list[JobRequirement]) -> tuple[list[JobRequirement], int]:
        output: list[JobRequirement] = []
        locations: dict[str, int] = {}
        priority = {
            RequirementImportance.REQUIRED: 3,
            RequirementImportance.MANUAL: 2,
            RequirementImportance.PREFERRED: 1,
            RequirementImportance.EXCLUDED: 0,
        }
        merged = 0
        for item in requirements:
            normalized = (item.normalized_value or self.skills.normalize(item.text)).casefold()
            if normalized not in locations:
                copied = item.model_copy(update={"normalized_value": normalized, "sort_order": len(output)})
                locations[normalized] = len(output)
                output.append(copied)
                continue
            merged += 1
            index = locations[normalized]
            current = output[index]
            if priority[item.importance] > priority[current.importance]:
                output[index] = item.model_copy(update={"normalized_value": normalized, "sort_order": index})
        return output, merged

    def apply_to_job(self, job: JobDescription, requirements: list[JobRequirement]) -> JobDescription:
        active = [item for item in requirements if item.enabled and item.importance != RequirementImportance.EXCLUDED]
        required_skills = [
            item.normalized_value or self.skills.normalize(item.text)
            for item in active
            if item.category == RequirementCategory.SKILL and item.importance == RequirementImportance.REQUIRED
        ]
        preferred_skills = [
            item.normalized_value or self.skills.normalize(item.text)
            for item in active
            if item.category == RequirementCategory.SKILL and item.importance == RequirementImportance.PREFERRED
        ]
        certifications = [item.text for item in active if item.category == RequirementCategory.CERTIFICATION]
        education = next((item.text for item in active if item.category == RequirementCategory.EDUCATION), None)
        return job.model_copy(
            update={
                "requirements": requirements,
                "required_skills": required_skills,
                "preferred_skills": preferred_skills,
                "certification_requirements": certifications,
                "education_requirements": education,
            }
        )

    def save_version(
        self,
        repository: Repository,
        job: JobDescription,
        requirements: list[JobRequirement],
        actor: str,
        change_summary: str = "Requirements confirmed for analysis",
    ) -> tuple[JobDescription, JobRequirementVersion, bool]:
        if job.id is None:
            raise ValueError("Save the job before creating a requirement version.")
        normalized, _ = self.merge_duplicates(requirements)
        latest = repository.latest_requirement_version(job.id)
        current_payload = json.dumps([item.model_dump(mode="json") for item in normalized], sort_keys=True)
        if latest:
            latest_payload = json.dumps([item.model_dump(mode="json") for item in latest.requirements], sort_keys=True)
            if latest_payload == current_payload:
                job = self.apply_to_job(job, latest.requirements).model_copy(update={"requirement_version_id": latest.id})
                repository.update_job(job)
                return job, latest, False
        version = JobRequirementVersion(
            job_id=job.id,
            version_number=(latest.version_number + 1) if latest else 1,
            requirements=normalized,
            change_summary=change_summary,
            actor=actor,
        )
        version = repository.add_requirement_version(version)
        job = self.apply_to_job(job, normalized).model_copy(update={"requirement_version_id": version.id})
        repository.update_job(job)
        repository.add_audit_event(
            AuditEvent(
                event_type="requirement_version_created",
                entity_type="job",
                entity_id=job.id,
                actor=actor,
                details={"version_id": version.id, "version_number": version.version_number},
            )
        )
        return job, version, True

    def _skill(
        self,
        value: str,
        importance: RequirementImportance,
        source: str,
        sort_order: int,
    ) -> JobRequirement:
        return JobRequirement(
            text=value,
            normalized_value=self.skills.normalize(value),
            category=RequirementCategory.SKILL,
            importance=importance,
            evaluation_method=RequirementEvaluationMethod.RESUME_EVIDENCE,
            source=source,
            sort_order=sort_order,
        )
