from __future__ import annotations

import re
from pathlib import Path

from database.repository import Repository
from models.domain import AuditEvent, CandidateProfile, EvidenceSnippet, MatchResult, RequirementAssessment
from services.auth_service import AccessContext


class PrivacyService:
    """Presentation-layer anonymization. Original records remain restricted in storage."""

    @staticmethod
    def anonymous_label(candidate: CandidateProfile) -> str:
        if candidate.id is not None:
            return f"Candidate {candidate.id:03d}"
        return f"Candidate {candidate.file_hash[:6].upper()}"

    @staticmethod
    def can_reveal(access: AccessContext, demo_mode: bool) -> bool:
        denied_roles = {"viewer", "auditor", "demo"}
        return access.authenticated and not demo_mode and not denied_roles.intersection(
            {role.casefold() for role in access.roles}
        )

    @classmethod
    def reveal_identity(
        cls,
        repository: Repository,
        candidate_id: int,
        job_id: int,
        access: AccessContext,
        demo_mode: bool,
    ) -> None:
        """Authorize and audit a reveal before the UI receives permission to show identity fields."""
        if not cls.can_reveal(access, demo_mode):
            raise PermissionError("This access mode cannot reveal candidate identity.")
        if repository.get_candidate(candidate_id) is None:
            raise ValueError("Candidate record was not found.")
        repository.add_audit_event(
            AuditEvent(
                event_type="candidate_identity_revealed",
                entity_type="candidate",
                entity_id=candidate_id,
                actor=access.user_id or access.display_name,
                details={"job_id": job_id},
            )
        )

    @classmethod
    def redact_text(cls, value: str, candidate: CandidateProfile) -> str:
        text = value or ""
        replacements = [candidate.email, candidate.phone]
        if candidate.candidate_name and candidate.candidate_name != "Name requires verification":
            replacements.append(candidate.candidate_name)
        for item in replacements:
            if item:
                text = re.sub(re.escape(item), "[identity hidden]", text, flags=re.IGNORECASE)
        for entry in candidate.employment_history:
            if entry.organization:
                text = re.sub(re.escape(entry.organization), "[organization hidden]", text, flags=re.IGNORECASE)
        text = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[email hidden]", text)
        text = re.sub(r"(?i)https?://\S+|www\.\S+|(?:linkedin|github)\.com/\S+", "[link hidden]", text)
        text = re.sub(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)", "[phone hidden]", text)
        text = re.sub(
            r"(?i)\b\d{1,5}\s+[A-Za-z0-9 .'-]{2,40}\s(?:street|st|road|rd|avenue|ave|lane|ln|drive|dr|boulevard|blvd)\b[^\n,;]*",
            "[address hidden]",
            text,
        )
        return text

    @classmethod
    def anonymize_candidate(cls, candidate: CandidateProfile) -> CandidateProfile:
        label = cls.anonymous_label(candidate)
        suffix = Path(candidate.file_name).suffix.lower() or ".document"
        evidence = {
            skill: [
                snippet.model_copy(update={"snippet": cls.redact_text(snippet.snippet, candidate)})
                for snippet in snippets
            ]
            for skill, snippets in candidate.skill_evidence.items()
        }
        employment = [
            entry.model_copy(
                update={
                    "organization": "[organization hidden]" if entry.organization else None,
                    "evidence": cls.redact_text(entry.evidence, candidate),
                }
            )
            for entry in candidate.employment_history
        ]
        return candidate.model_copy(
            deep=True,
            update={
                "candidate_name": label,
                "email": None,
                "phone": None,
                "file_hash": f"anonymous-{candidate.id or candidate.file_hash[:6]}",
                "file_name": f"{label.lower().replace(' ', '-')}-resume{suffix}",
                "raw_text": "",
                "skill_evidence": evidence,
                "employment_history": employment,
                "projects": [cls.redact_text(item, candidate) for item in candidate.projects],
                "education": [cls.redact_text(item, candidate) for item in candidate.education],
                "certifications": [cls.redact_text(item, candidate) for item in candidate.certifications],
                "azure_entities": [],
                "reviewer_comments": [],
            },
        )

    @classmethod
    def anonymize_match(cls, result: MatchResult, candidate: CandidateProfile) -> MatchResult:
        assessments: list[RequirementAssessment] = []
        for assessment in result.assessments:
            evidence = [
                EvidenceSnippet(
                    qualification=item.qualification,
                    snippet=cls.redact_text(item.snippet, candidate),
                    source=item.source,
                    confidence=item.confidence,
                )
                for item in assessment.evidence
            ]
            assessments.append(assessment.model_copy(update={"evidence": evidence}))
        return result.model_copy(deep=True, update={"assessments": assessments})
