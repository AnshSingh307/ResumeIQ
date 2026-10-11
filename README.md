# ResumeIQ — Intelligent Resume Insights

ResumeIQ is a privacy-aware Streamlit workspace for comparing evidence in PDF/DOCX resumes with explicit job requirements. It reports qualification coverage and source excerpts; it does not predict job performance or make hiring decisions.

## Product workflow

- **Dashboard:** operational KPIs, coverage chart, anonymous-review status, recent correction/version activity, and an analysis shortcut.
- **Resume Analyzer:** multi-file upload, deterministic job-description quality checks, an editable requirement table, immutable requirement versions, progress, and evidence-linked results.
- **Candidates:** anonymous or identified review, authorized audited identity reveal, corrected extraction history, recalculated analyses, comparison, evidence, and sanitized CSV/Excel/JSON exports.
- **Settings:** anonymous-review preference, processing, theme, retention, permissions, authentication context, and Azure readiness controls.

The local pipeline keeps the existing deterministic extraction and matching design: signature/size validation, SHA-256 duplicate detection, PDF/DOCX extraction, conservative profile extraction, skill-synonym normalization, requirement assessment, and SQLite persistence. Protected or sensitive criteria are blocked from matching.

## Run locally (Windows PowerShell)

Python 3.11 or newer is recommended.

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python sample_data\generate_samples.py
python -m pytest -q
python -m streamlit run app.py
```

Expected result: tests pass and Streamlit shows a URL such as `http://localhost:8501`. If activation is blocked, use `.\.venv\Scripts\python.exe` in place of `python`.

## Safe fictional demo

Set these values in `.env`, then start Streamlit:

```dotenv
RESUMEIQ_DEMO_MODE=true
RESUMEIQ_DEMO_DATA_DIR=./data/demo
RESUMEIQ_AUTH_REQUIRED=false
RESUMEIQ_ANONYMOUS_DEFAULT=true
```

Demo mode seeds bundled fictional resumes into an isolated database. Anonymous review is forced on; uploads, identity reveal, corrections, deletion, retention changes, Azure calls, and settings changes are disabled. It never reads the normal `RESUMEIQ_DATA_DIR` database.

## The four advanced review controls

- **Anonymous review:** uses a stable `Candidate 001`-style label without modifying the stored profile or the matching inputs. Screen evidence and all three export formats are sanitized. An authorized reveal is explicit and audit logged. Automated free-text redaction reduces risk but cannot guarantee anonymity.
- **Corrections:** an authorized reviewer can correct validated extracted fields with a required reason. The original value and attribution remain in immutable correction history; current analyses are recalculated, and a correction can be reverted. The uploaded document never changes.
- **Job quality:** blocking protected criteria prevent analysis. Deterministic warnings such as vague wording, duplicates, mismatches, and unrealistic experience need explicit acknowledgement; the acknowledgement is audited. ResumeIQ does not invent a numerical bias score.
- **Requirement manager:** every active row has text, normalized value, category, importance, evaluation method, notes, and status. Excluded rows do not score; manual rows remain manual. Confirmed changes create immutable versions so older analyses keep their requirement snapshot.

## Architecture and persistence

- SQLite stores validated candidate, job, match, correction, requirement-version, quality-check, audit, and setting records across sessions.
- Startup migrations are additive and idempotent (`CREATE TABLE/INDEX IF NOT EXISTS`); existing candidate, job, match, setting, and audit tables are not replaced.
- Local source files live below `RESUMEIQ_DATA_DIR` and are never committed.
- Production real-data mode requires Azure App Service Authentication, a `/home` data directory, and private Azure Blob Storage.
- Blob authentication supports App Service managed identity through `AZURE_STORAGE_ACCOUNT_URL` (preferred) or a connection string stored only in a protected application setting/Key Vault reference.
- SQLite under App Service `/home` is deliberately limited to a single-instance controlled demonstration. It is not a shared scale-out database; use a managed relational database before enabling multiple instances.

## Azure deployment

The repository contains:

- `azure/startup.sh` — binds Streamlit to `0.0.0.0` and Azure's assigned port.
- `azure/appservice-settings.example.json` — authenticated real-data settings.
- `azure/public-demo-settings.example.json` — isolated fictional public-demo settings.
- `docs/deployment-azure.md` — the complete beginner deployment and cost-safety guide.

Do not assume that a plan, region, quota, or free grant is available. Verify the current offer and displayed price in the student's own Azure portal before provisioning. No Azure deployment is proven merely by these files.

## Security and responsible use

- Keep `.env`, App Service settings, resume sources, databases, certificates, and `.streamlit/secrets.*` out of Git.
- Enable App Service Authentication with Microsoft Entra ID before exposing real candidate records.
- Keep Blob containers private; anonymous access is not used.
- File signatures and size limits are validation, not malware scanning. Add scanning/content disarm before general public upload.
- Contact details identify a record but do not affect matching.
- “Not found” means ResumeIQ found no evidence in parsed text; it does not prove the candidate lacks a qualification.
- Human review remains mandatory. Read [docs/privacy.md](docs/privacy.md) before using non-fictional data.

## Verification

```powershell
python -m pytest -q
python -m streamlit run app.py
```

The automated suite covers parsing, malformed uploads, duplicates, deterministic matching, anonymous exports, reveal/correction authorization, correction/reversion recalculation, quality gates, requirement versions, additive migration, persistence, authentication, demo isolation, multi-file analysis, filters/sorting, production guardrails, and app imports/startup. See [docs/testing.md](docs/testing.md). Azure calls and a live website require the user's own subscription and are not claimed as tested without them.

## Repository map

```text
app.py             application composition and four-section navigation
components/        shared premium UI and evidence views
config/            environment settings and skill synonyms
database/          SQLite repository
models/            validated domain models
pages/             Dashboard, Resume Analyzer, Candidates, Settings
services/          parsing, extraction, matching, auth, storage, exports
sample_data/       bundled fictional resumes and jobs
tests/             unit, integration, workflow, and smoke tests
azure/             App Service examples
docs/              architecture, privacy, and deployment guides
```
