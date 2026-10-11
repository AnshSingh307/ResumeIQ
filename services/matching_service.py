from __future__ import annotations

import re

from models.domain import (
    CandidateProfile,
    EvidenceSnippet,
    JobDescription,
    MatchResult,
    RequirementCategory,
    RequirementAssessment,
    RequirementEvaluationMethod,
    RequirementImportance,
    RequirementStatus,
    ScoreWeights,
)
from services.skill_service import SemanticSimilarityService, SkillService


class MatchingService:
    def __init__(
        self,
        skill_service: SkillService | None = None,
        semantic_service: SemanticSimilarityService | None = None,
    ):
        self.skills = skill_service or SkillService()
        self.semantic = semantic_service or SemanticSimilarityService()

    def analyze(
        self,
        candidate: CandidateProfile,
        job: JobDescription,
        weights: ScoreWeights | None = None,
    ) -> MatchResult:
        if candidate.id is None or job.id is None:
            raise ValueError("Candidate and job must be saved before matching.")
        weights = weights or ScoreWeights()
        assessments: list[RequirementAssessment] = []
        required = self._assess_skills(candidate, job.required_skills, "required_skill")
        preferred = self._assess_skills(candidate, job.preferred_skills, "preferred_skill")
        assessments.extend(required)
        assessments.extend(preferred)

        experience_score = 0.0
        if job.minimum_experience_years is not None:
            experience_assessment, experience_score = self._assess_experience(candidate, job.minimum_experience_years)
            assessments.append(experience_assessment)

        certification_score = 0.0
        if job.certification_requirements:
            cert_assessments = self._assess_certifications(candidate, job.certification_requirements)
            assessments.extend(cert_assessments)
            certification_score = self._coverage(cert_assessments)

        if job.education_requirements:
            assessments.append(self._assess_education(candidate, job.education_requirements))

        represented = {
            (RequirementCategory.SKILL, RequirementImportance.REQUIRED),
            (RequirementCategory.SKILL, RequirementImportance.PREFERRED),
            (RequirementCategory.EXPERIENCE, RequirementImportance.REQUIRED),
            (RequirementCategory.CERTIFICATION, RequirementImportance.REQUIRED),
            (RequirementCategory.CERTIFICATION, RequirementImportance.PREFERRED),
            (RequirementCategory.EDUCATION, RequirementImportance.MANUAL),
        }
        for requirement in job.requirements:
            if not requirement.enabled or requirement.importance == RequirementImportance.EXCLUDED:
                continue
            needs_manual = (
                requirement.importance == RequirementImportance.MANUAL
                or requirement.evaluation_method == RequirementEvaluationMethod.HUMAN_ONLY
                or requirement.category in {RequirementCategory.RESPONSIBILITY, RequirementCategory.OTHER}
                or (requirement.category, requirement.importance) not in represented
            )
            if needs_manual and not any(
                item.requirement.casefold() == requirement.text.casefold() for item in assessments
            ):
                category = requirement.category.value
                assessments.append(
                    RequirementAssessment(
                        requirement=requirement.text,
                        category=category if category in {"experience", "certification", "education", "responsibility", "other"} else "other",
                        status=RequirementStatus.MANUAL_VERIFY,
                        explanation="This configured requirement is reserved for human verification and is excluded from numeric coverage.",
                    )
                )

        required_score = self._coverage(required)
        preferred_score = self._coverage(preferred)
        semantic_score = self.semantic.similarity(candidate.raw_text, job.description)
        raw_weights = weights.model_dump()
        category_scores: dict[str, float] = {}
        if any(item.status != RequirementStatus.MANUAL_VERIFY for item in required):
            category_scores["required_skills"] = required_score
        if any(item.status != RequirementStatus.MANUAL_VERIFY for item in preferred):
            category_scores["preferred_skills"] = preferred_score
        if job.minimum_experience_years is not None:
            category_scores["experience"] = experience_score
        if job.certification_requirements:
            category_scores["certifications"] = certification_score
        active_weight = sum(raw_weights[key] for key in category_scores)
        composite = (
            sum(score * raw_weights[key] for key, score in category_scores.items()) / active_weight
            if active_weight > 0
            else 0.0
        )
        return MatchResult(
            candidate_id=candidate.id,
            job_id=job.id,
            required_coverage=required_score,
            preferred_coverage=preferred_score,
            experience_coverage=experience_score,
            certification_coverage=certification_score,
            semantic_similarity=semantic_score,
            composite_indicator=round(composite, 2),
            assessments=assessments,
            explanation=(
                "This is a deterministic coverage indicator based on user-configured requirements and weights. "
                "The semantic metric is separate and is not proof of a qualification. Human review is required."
            ),
            requirement_version_id=job.requirement_version_id,
        )

    def _assess_skills(
        self, candidate: CandidateProfile, requirements: list[str], category: str
    ) -> list[RequirementAssessment]:
        candidate_skills = {self.skills.normalize(skill): skill for skill in candidate.skills}
        results: list[RequirementAssessment] = []
        for requirement in requirements:
            normalized = self.skills.normalize(requirement)
            if self.skills.is_sensitive_requirement(requirement):
                results.append(
                    RequirementAssessment(
                        requirement=requirement,
                        category=category,
                        status=RequirementStatus.MANUAL_VERIFY,
                        explanation="Excluded from matching because it may refer to a protected or sensitive characteristic.",
                    )
                )
                continue
            matched_key = candidate_skills.get(normalized)
            if matched_key:
                snippets = candidate.skill_evidence.get(matched_key, candidate.skill_evidence.get(normalized, []))
                results.append(
                    RequirementAssessment(
                        requirement=requirement,
                        category=category,
                        status=RequirementStatus.MATCHED,
                        evidence=snippets[:3],
                        explanation="A normalized exact/synonym match was found with resume evidence.",
                    )
                )
            else:
                results.append(
                    RequirementAssessment(
                        requirement=requirement,
                        category=category,
                        status=RequirementStatus.NOT_FOUND,
                        explanation="No verifiable exact or configured-synonym evidence was found in the resume.",
                    )
                )
        return results

    @staticmethod
    def _assess_education(candidate: CandidateProfile, requirement: str) -> RequirementAssessment:
        # Education equivalency is context-dependent. Surface literal evidence but leave
        # equivalency and job-relatedness to a reviewer instead of scoring it.
        evidence = [
            EvidenceSnippet(qualification=requirement, snippet=item)
            for item in candidate.education[:3]
        ]
        return RequirementAssessment(
            requirement=requirement,
            category="education",
            status=RequirementStatus.MANUAL_VERIFY,
            evidence=evidence,
            explanation=(
                "Education evidence is shown for manual equivalency and job-relatedness review; "
                "it is deliberately excluded from the numeric indicator."
            ),
        )

    @staticmethod
    def _assess_experience(candidate: CandidateProfile, minimum: float) -> tuple[RequirementAssessment, float]:
        if candidate.years_experience is None:
            return (
                RequirementAssessment(
                    requirement=f"{minimum:g}+ years relevant experience",
                    category="experience",
                    status=RequirementStatus.UNCERTAIN,
                    explanation="The resume did not explicitly state a reliable total; manual timeline review is required.",
                ),
                0.0,
            )
        evidence = EvidenceSnippet(
            qualification="experience",
            snippet=f"Resume explicitly states {candidate.years_experience:g} years of experience.",
        )
        if candidate.years_experience >= minimum:
            return (
                RequirementAssessment(
                    requirement=f"{minimum:g}+ years relevant experience",
                    category="experience",
                    status=RequirementStatus.MATCHED,
                    evidence=[evidence],
                    explanation="The explicitly stated experience meets the numeric threshold; relevance still needs review.",
                ),
                100.0,
            )
        return (
            RequirementAssessment(
                requirement=f"{minimum:g}+ years relevant experience",
                category="experience",
                status=RequirementStatus.NOT_FOUND,
                evidence=[evidence],
                explanation="The explicitly stated experience is below the configured threshold.",
            ),
            round(min(candidate.years_experience / minimum, 1.0) * 100, 2) if minimum else 100.0,
        )

    @staticmethod
    def _assess_certifications(
        candidate: CandidateProfile, requirements: list[str]
    ) -> list[RequirementAssessment]:
        resume_text = " ".join(candidate.certifications).casefold()
        results: list[RequirementAssessment] = []
        for requirement in requirements:
            matched = re.search(rf"(?<!\w){re.escape(requirement.casefold())}(?!\w)", resume_text) is not None
            results.append(
                RequirementAssessment(
                    requirement=requirement,
                    category="certification",
                    status=RequirementStatus.MATCHED if matched else RequirementStatus.NOT_FOUND,
                    evidence=(
                        [EvidenceSnippet(qualification=requirement, snippet=next(c for c in candidate.certifications if requirement.casefold() in c.casefold()))]
                        if matched
                        else []
                    ),
                    explanation="Certification text was found." if matched else "Certification was not found in the extracted certification section.",
                )
            )
        return results

    @staticmethod
    def _coverage(assessments: list[RequirementAssessment]) -> float:
        eligible = [item for item in assessments if item.status != RequirementStatus.MANUAL_VERIFY]
        if not eligible:
            return 0.0
        matched = sum(item.status == RequirementStatus.MATCHED for item in eligible)
        return round(matched / len(eligible) * 100, 2)
