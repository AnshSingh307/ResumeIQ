from __future__ import annotations

from typing import Any

from database.repository import Repository
from models.domain import AuditEvent, CandidateCorrection, CandidateProfile, utc_now
from services.auth_service import AccessContext
from services.matching_service import MatchingService


CORRECTABLE_FIELDS = {
    "candidate_name",
    "email",
    "phone",
    "skills",
    "education",
    "employment_history",
    "projects",
    "certifications",
    "years_experience",
    "parse_warnings",
    "reviewer_comments",
}


class CandidateCorrectionService:
    def __init__(self, repository: Repository, matcher: MatchingService):
        self.repository = repository
        self.matcher = matcher

    @staticmethod
    def can_correct(access: AccessContext, demo_mode: bool) -> bool:
        denied_roles = {"viewer", "auditor", "demo"}
        return access.authenticated and not demo_mode and not denied_roles.intersection(
            {role.casefold() for role in access.roles}
        )

    def correct(
        self,
        candidate_id: int,
        field_name: str,
        corrected_value: Any,
        reason: str,
        access: AccessContext,
        demo_mode: bool,
    ) -> tuple[CandidateCorrection, int]:
        if not self.can_correct(access, demo_mode):
            raise PermissionError("This access mode cannot correct candidate data.")
        actor = access.user_id or access.display_name
        if field_name not in CORRECTABLE_FIELDS:
            raise ValueError("This field is not eligible for reviewer correction.")
        if len(reason.strip()) < 3:
            raise ValueError("Enter a meaningful correction reason.")
        candidate = self.repository.get_candidate(candidate_id)
        if candidate is None:
            raise ValueError("Candidate record was not found.")
        original_value = getattr(candidate, field_name)
        payload = candidate.model_dump(mode="python")
        payload[field_name] = corrected_value
        updated = CandidateProfile.model_validate(payload)
        correction = self.repository.add_correction(
            CandidateCorrection(
                candidate_id=candidate_id,
                field_name=field_name,
                original_value=original_value,
                corrected_value=getattr(updated, field_name),
                reason=reason.strip(),
                actor=actor,
            )
        )
        self.repository.update_candidate(updated)
        self.repository.add_audit_event(
            AuditEvent(
                event_type="candidate_correction_created",
                entity_type="candidate",
                entity_id=candidate_id,
                actor=actor,
                details={"correction_id": correction.id, "field_name": field_name},
            )
        )
        return correction, self._recalculate(candidate_id)

    def revert(
        self,
        correction_id: int,
        access: AccessContext,
        demo_mode: bool,
    ) -> int:
        if not self.can_correct(access, demo_mode):
            raise PermissionError("This access mode cannot revert candidate corrections.")
        actor = access.user_id or access.display_name
        correction = self.repository.get_correction(correction_id)
        if correction is None or not correction.active:
            raise ValueError("This correction is unavailable or already reverted.")
        candidate = self.repository.get_candidate(correction.candidate_id)
        if candidate is None:
            raise ValueError("Candidate record was not found.")
        latest_active = next(
            (
                item
                for item in self.repository.list_candidate_corrections(candidate.id)
                if item.field_name == correction.field_name and item.active
            ),
            None,
        )
        if latest_active is None or latest_active.id != correction.id:
            raise ValueError("Revert the latest active correction for this field first.")
        payload = candidate.model_dump(mode="python")
        payload[correction.field_name] = correction.original_value
        self.repository.update_candidate(CandidateProfile.model_validate(payload))
        correction.active = False
        correction.reverted_at = utc_now()
        correction.reverted_by = actor
        self.repository.update_correction(correction)
        self.repository.add_audit_event(
            AuditEvent(
                event_type="candidate_correction_reverted",
                entity_type="candidate",
                entity_id=candidate.id,
                actor=actor,
                details={"correction_id": correction.id, "field_name": correction.field_name},
            )
        )
        return self._recalculate(candidate.id)

    def _recalculate(self, candidate_id: int) -> int:
        candidate = self.repository.get_candidate(candidate_id)
        if candidate is None:
            return 0
        current_matches = [item for item in self.repository.list_matches() if item.candidate_id == candidate_id]
        count = 0
        for old in current_matches:
            job = self.repository.get_job(old.job_id)
            if job is None:
                continue
            self.repository.save_match(self.matcher.analyze(candidate, job))
            count += 1
        return count
