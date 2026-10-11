from __future__ import annotations

import re
from pathlib import Path

from models.domain import CandidateProfile, EmploymentEntry, EvidenceSnippet, ProcessingStatus
from services.skill_service import SkillService


EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?\d[\d ()-]{7,}\d)(?!\d)")
YEARS_PATTERN = re.compile(r"\b(\d{1,2}(?:\.\d)?)\+?\s+years?\s+(?:of\s+)?experience\b", re.IGNORECASE)


class ProfileExtractionService:
    """Conservative rule-based extraction; uncertain information is left for human review."""

    def __init__(self, skill_service: SkillService | None = None):
        self.skill_service = skill_service or SkillService()

    def extract(self, file_name: str, file_hash: str, text: str) -> CandidateProfile:
        lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
        skill_snippets = self.skill_service.extract(text)
        evidence = {
            skill: [EvidenceSnippet(qualification=skill, snippet=snippet) for snippet in snippets]
            for skill, snippets in skill_snippets.items()
        }
        warnings: list[str] = []
        name = self._extract_name(lines)
        if name == "Name requires verification":
            warnings.append("Candidate name was not confidently extracted.")
        years = self._extract_years(text)
        if years is None:
            warnings.append("Total years of experience was not explicitly stated; verify manually.")
        profile = CandidateProfile(
            file_name=Path(file_name).name,
            file_hash=file_hash,
            candidate_name=name,
            email=self._first(EMAIL_PATTERN, text),
            phone=self._first(PHONE_PATTERN, text),
            skills=sorted(evidence),
            skill_evidence=evidence,
            education=self._section_lines(lines, {"education", "academic background", "qualifications"}),
            employment_history=self._employment(lines),
            projects=self._section_lines(lines, {"projects", "selected projects"}),
            certifications=self._section_lines(lines, {"certifications", "certificates", "licenses"}),
            years_experience=years,
            raw_text=text,
            parse_warnings=warnings,
            processing_status=ProcessingStatus.NEEDS_REVIEW if warnings else ProcessingStatus.PROCESSED,
        )
        return profile

    @staticmethod
    def _first(pattern: re.Pattern[str], text: str) -> str | None:
        match = pattern.search(text)
        return match.group(0).strip() if match else None

    @staticmethod
    def _extract_name(lines: list[str]) -> str:
        excluded = {"resume", "curriculum vitae", "cv", "profile", "summary"}
        for line in lines[:5]:
            if (
                1 < len(line.split()) <= 5
                and line.casefold() not in excluded
                and "@" not in line
                and not any(char.isdigit() for char in line)
                and re.fullmatch(r"[A-Za-z][A-Za-z .'-]+", line)
            ):
                return line.title() if line.isupper() else line
        return "Name requires verification"

    @staticmethod
    def _extract_years(text: str) -> float | None:
        values = [float(match.group(1)) for match in YEARS_PATTERN.finditer(text)]
        return max(values) if values else None

    @staticmethod
    def _section_lines(lines: list[str], headings: set[str], max_items: int = 8) -> list[str]:
        results: list[str] = []
        collecting = False
        known_headings = {
            "summary", "skills", "technical skills", "experience", "work experience", "employment",
            "education", "academic background", "qualifications", "projects", "selected projects",
            "certifications", "certificates", "licenses", "awards", "contact",
        }
        for line in lines:
            normalized = line.strip(": ").casefold()
            if normalized in headings:
                collecting = True
                continue
            if collecting and normalized in known_headings:
                break
            if collecting:
                results.append(line.lstrip("-• "))
                if len(results) >= max_items:
                    break
        return results

    @staticmethod
    def _employment(lines: list[str]) -> list[EmploymentEntry]:
        evidence = ProfileExtractionService._section_lines(lines, {"experience", "work experience", "employment"}, 12)
        return [EmploymentEntry(evidence=line, title="Role requires verification") for line in evidence]

