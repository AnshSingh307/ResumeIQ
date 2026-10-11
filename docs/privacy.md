# Privacy and responsible-use notice

Resumes contain personal information. The local demonstration stores uploaded files and extracted text under the configured `RESUMEIQ_DATA_DIR`; access to that computer therefore controls access to resume data. Use fictional sample data for demonstrations.

ResumeIQ deliberately excludes sensitive or protected characteristics such as age, gender, religion, caste, race, nationality, disability, marital status, and photographs from its matching logic. The quality checker blocks enabled protected criteria before analysis. Users must not add proxies for those characteristics. Names and contact details never contribute to coverage.

## Anonymous review

Anonymous mode creates a presentation-only copy with a stable neutral label, sanitized filename/hash, no contact fields, no raw text, and redacted evidence. The database ID and original validated profile stay unchanged; matching runs on the original non-identity qualification data before the display copy is made. Candidate tables, comparisons, evidence panels, and CSV/Excel/JSON downloads use the anonymous copy. Even after an authorized on-screen reveal, downloads remain anonymous while the workspace setting is active.

Automated redaction is risk reduction, not guaranteed anonymization. A free-form sentence may indirectly identify someone through an institution, unusual project, certification, location, or other context. Review generated exports before sharing them. Public demo mode forces anonymous review and disables reveals and corrections.

An authenticated local/recruiter role may deliberately reveal identity outside demo mode. Viewer, auditor, and demo roles cannot. Every successful reveal is audit logged without copying contact details into the event.

## Reviewer corrections

A correction changes the validated working profile, not the uploaded source document. The correction record retains candidate ID, field, original value, corrected value, reason, reviewer, creation time, and any later reversion. Current candidate-to-job matches are recalculated and appended to analysis history. A correction is reviewer-attributed information, not automatically verified truth. Only the latest active correction for a field can be reverted first, preserving a coherent history.

## Job and requirement safeguards

Sensitive findings are blocking. Other deterministic warnings require human acknowledgement before analysis and the acknowledgement is audited. Requirement snapshots are immutable: edits create a later version rather than silently changing what an older analysis used. Excluded rows do not affect coverage; manual-verification rows cannot become automatic matches from semantic similarity.

No model is trained on uploaded resumes. Azure calls are disabled by default. If a user enables an Azure service, data leaves the local process and becomes subject to that resource's region, access, logging, retention, network, and contractual configuration. PII or entity redaction cannot guarantee anonymization.

The application does not automatically reject candidates. “Not found” means evidence was not located in the parsed resume; it is not proof that the candidate lacks the qualification. “Uncertain” and “manual verification” require a reviewer to inspect the source document.

