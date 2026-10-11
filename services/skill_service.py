from __future__ import annotations

import json
import re
from pathlib import Path


PROTECTED_OR_SENSITIVE_TERMS = {
    "age",
    "gender",
    "sex",
    "religion",
    "caste",
    "nationality",
    "race",
    "ethnicity",
    "marital status",
    "disability",
    "pregnancy",
    "photograph",
    "photo",
}


class SkillService:
    def __init__(self, dictionary_path: str | Path | None = None):
        path = Path(dictionary_path) if dictionary_path else Path(__file__).parents[1] / "config" / "skills.json"
        self.skills: dict[str, list[str]] = json.loads(path.read_text(encoding="utf-8"))
        self.alias_to_canonical = {
            alias.casefold(): canonical for canonical, aliases in self.skills.items() for alias in aliases
        }

    @staticmethod
    def _contains_phrase(text: str, phrase: str) -> bool:
        return re.search(rf"(?<![\w]){re.escape(phrase)}(?![\w])", text, flags=re.IGNORECASE) is not None

    def normalize(self, value: str) -> str:
        cleaned = " ".join(value.casefold().strip().split())
        return self.alias_to_canonical.get(cleaned, cleaned)

    def is_sensitive_requirement(self, value: str) -> bool:
        return bool(self.sensitive_terms_found(value))

    def sensitive_terms_found(self, value: str) -> list[str]:
        normalized = self.normalize(value)
        return sorted(term for term in PROTECTED_OR_SENSITIVE_TERMS if self._contains_phrase(normalized, term))

    def extract(self, text: str) -> dict[str, list[str]]:
        evidence: dict[str, list[str]] = {}
        sentences = self.sentences(text)
        for canonical, aliases in self.skills.items():
            snippets = [
                sentence.strip()
                for sentence in sentences
                if any(self._contains_phrase(sentence, alias) for alias in aliases)
            ]
            if snippets:
                evidence[canonical] = list(dict.fromkeys(snippets))[:5]
        return evidence

    @staticmethod
    def sentences(text: str) -> list[str]:
        # spaCy is optional because its trained models are large. A blank pipeline still
        # provides robust sentence boundaries without downloading a language model.
        try:
            import spacy

            nlp = spacy.blank("en")
            nlp.add_pipe("sentencizer")
            chunks = [sentence.text for sentence in nlp(text).sents]
            return [" ".join(chunk.strip(" •\t").split()) for chunk in chunks if chunk.strip(" •\t")]
        except (ImportError, ValueError):
            pass
        chunks = re.split(r"(?<=[.!?])\s+|\n+|(?=•)", text)
        return [" ".join(chunk.strip(" •\t").split()) for chunk in chunks if chunk.strip(" •\t")]

    def parse_list(self, value: str) -> list[str]:
        items = [item.strip() for item in re.split(r"[,;\n]", value)]
        normalized: list[str] = []
        for item in items:
            if not item:
                continue
            skill = self.normalize(item)
            if skill not in normalized:
                normalized.append(skill)
        return normalized


class SemanticSimilarityService:
    """Optional semantic metric; it never establishes possession of a qualification."""

    def __init__(self, provider: str = "tfidf", sentence_model: str = "all-MiniLM-L6-v2"):
        self.provider = provider
        self.sentence_model = sentence_model
        self._model = None

    def similarity(self, resume_text: str, job_text: str) -> float:
        if not resume_text.strip() or not job_text.strip():
            return 0.0
        if self.provider == "sentence-transformers":
            return self._sentence_transformer_similarity(resume_text, job_text)
        return self._tfidf_similarity(resume_text, job_text)

    @staticmethod
    def _tfidf_similarity(resume_text: str, job_text: str) -> float:
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
        except ImportError:
            return 0.0
        vectors = TfidfVectorizer(stop_words="english").fit_transform([resume_text, job_text])
        return round(float(cosine_similarity(vectors[0:1], vectors[1:2])[0][0]) * 100, 2)

    def _sentence_transformer_similarity(self, resume_text: str, job_text: str) -> float:
        try:
            from sentence_transformers import SentenceTransformer
            from sklearn.metrics.pairwise import cosine_similarity
        except ImportError:
            return self._tfidf_similarity(resume_text, job_text)
        if self._model is None:
            self._model = SentenceTransformer(self.sentence_model)
        vectors = self._model.encode([resume_text[:12000], job_text[:12000]])
        return round(float(cosine_similarity([vectors[0]], [vectors[1]])[0][0]) * 100, 2)

