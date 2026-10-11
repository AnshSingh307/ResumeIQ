# ResumeIQ architecture and viva notes

## Local request flow

1. Streamlit receives a PDF or DOCX in memory.
2. `LocalStorageService` validates extension, signature, size, and safe path; SHA-256 enables duplicate detection.
3. `DocumentParser` uses PyMuPDF or python-docx. Optional Document Intelligence OCR is attempted only when explicitly enabled and local parsing fails.
4. `ProfileExtractionService` extracts conservative, evidence-linked facts. Unknown values stay unknown.
5. `MatchingService` normalizes configured synonyms and calculates deterministic requirement coverage. TF-IDF or optional Sentence Transformers supplies a separate semantic similarity metric.
6. `JobQualityService` blocks sensitive criteria and classifies deterministic warnings/suggestions before an analysis can run.
7. `RequirementService` validates editable rows, saves an immutable requirement version, and projects the active version into the existing matcher inputs.
8. SQLite stores validated Pydantic models, current analyses, analysis history, corrections, requirement versions, quality results, settings, and audit events.
9. `PrivacyService` creates presentation-only anonymous copies for screen and export; matching always receives the original validated profile.
10. Reports export CSV, Excel, or candidate JSON without making a hiring decision.

## Additive data model

The original `candidates`, `jobs`, `matches`, `audit_events`, and `app_settings` tables remain intact. Repository startup idempotently adds:

- `candidate_corrections`: append-only original/corrected values, reason, actor, timestamps, active/reverted state;
- `job_requirement_versions`: immutable validated requirement snapshots per job and sequential version number;
- `quality_check_results`: deterministic findings and acknowledgement state;
- `match_history`: each recalculated analysis with the requirement-version reference.

The current match stays in `matches` for fast screens; every save is also appended to `match_history`. Foreign keys cascade only when an authorized user deliberately deletes the parent candidate or job.

## Authorization boundaries

The UI omits controls for demo, viewer, and auditor roles, and the privacy/correction services repeat those checks before changing state. An identity reveal records only candidate/job identifiers and actor—not contact data. Corrections and reversions store the authenticated object ID when available. Demo mode always enables anonymous review.

## Why these choices

- **Streamlit:** a beginner can create a professional Python UI without maintaining a separate JavaScript application.
- **Pydantic:** rejects invalid data at module boundaries and gives every stored result a clear schema.
- **SQLite:** zero-cost, file-based persistence for a university demo. It is not the correct shared database for a multi-instance production deployment.
- **Deterministic scoring:** the same inputs and settings give the same result; each matched item has evidence. This is easier to test and defend than an opaque model-generated score.
- **Separate semantic similarity:** similar wording is useful context but does not prove the candidate owns a skill.
- **Feature flags:** the local MVP works without Azure credentials; each cloud dependency can be enabled and tested independently.

## Important viva distinction

ResumeIQ is a screening and evidence-organization assistant, not an automated decision system. A coverage percentage answers “how many explicitly configured requirements had verified text evidence?” It does not answer “should this person be hired?”

## Production gaps

Before real organizational use, formalize role assignment, centralized secrets, malware scanning, encrypted managed persistence, transactional/concurrency-safe migrations, accessibility testing, retention enforcement, legal review, bias/fairness evaluation, and an organizational appeal process. SQLite remains suitable only for the single-instance controlled demonstration described here.

