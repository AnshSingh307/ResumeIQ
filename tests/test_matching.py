from services.extraction_service import ProfileExtractionService
from services.matching_service import MatchingService
from services.skill_service import SemanticSimilarityService, SkillService
from models.domain import JobDescription, RequirementStatus, ScoreWeights


def candidate(text: str):
    item = ProfileExtractionService().extract("candidate.docx", "abc123", text)
    item.id = 1
    return item


def job(required: list[str], preferred: list[str] | None = None):
    item = JobDescription(title="Test job", description="Python SQL Azure role", required_skills=required, preferred_skills=preferred or [])
    item.id = 1
    return item


def matcher() -> MatchingService:
    return MatchingService(SkillService(), SemanticSimilarityService("tfidf"))


def test_skill_synonym_matching() -> None:
    profile = candidate("Sam Lee\n2 years of experience. Used sklearn for predictive projects.")
    result = matcher().analyze(profile, job(["scikit-learn"]))
    assert result.required_coverage == 100
    assert result.assessments[0].status == RequirementStatus.MATCHED
    assert "sklearn" in result.assessments[0].evidence[0].snippet


def test_missing_qualification_is_not_invented() -> None:
    profile = candidate("Sam Lee\nPython developer with 2 years of experience.")
    result = matcher().analyze(profile, job(["Python", "Kubernetes"]))
    assert result.required_coverage == 50
    missing = [item for item in result.assessments if item.status == RequirementStatus.NOT_FOUND]
    assert [item.requirement for item in missing] == ["Kubernetes"]
    assert missing[0].evidence == []


def test_requirement_coverage_and_configurable_weights() -> None:
    profile = candidate("Sam Lee\nPython developer with 2 years of experience. SQL reporting.")
    role = job(["Python", "SQL"], ["Docker"])
    result = matcher().analyze(profile, role, ScoreWeights(required_skills=1, preferred_skills=0, experience=0, certifications=0))
    assert result.required_coverage == 100
    assert result.preferred_coverage == 0
    assert result.composite_indicator == 100


def test_sensitive_characteristic_is_excluded_from_matching() -> None:
    profile = candidate("Sam Lee\nPython developer with 2 years of experience.")
    result = matcher().analyze(profile, job(["Python", "religion"]))
    sensitive = next(item for item in result.assessments if item.requirement == "religion")
    assert sensitive.status == RequirementStatus.MANUAL_VERIFY
    assert "protected" in sensitive.explanation


def test_unconfigured_categories_do_not_add_free_points() -> None:
    profile = candidate("Sam Lee\nKubernetes administrator with 2 years of experience.")
    result = matcher().analyze(profile, job(["Python"]))
    assert result.required_coverage == 0
    assert result.composite_indicator == 0

