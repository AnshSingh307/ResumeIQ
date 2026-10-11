# ResumeIQ verification guide

All automated tests use temporary databases or bundled fictional data. Do not point test runs at a real `RESUMEIQ_DATA_DIR`.

## Automated checks

From PowerShell in the repository root:

```powershell
.\.venv\Scripts\python.exe -m compileall -q app.py components config database models pages services tests
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

The suite covers PDF/DOCX parsing, multi-file uploads, duplicates, deterministic matching, protected-criteria exclusion, filters, exports, SQLite persistence, authentication, demo isolation, production guards, app startup, and the following advanced controls:

- stable anonymous identifiers and sanitized CSV, Excel, and JSON;
- reveal authorization and reveal audit events;
- correction reason, attribution, history, recalculation, reversion, and demo/viewer denial;
- quality blockers, warnings, suggestions, contradictions, acknowledgement, and audit events;
- requirement merging, validation, ordering, exclusion/manual behavior, immutable versions, and old-version preservation;
- additive schema initialization over a legacy candidate table.

## Local browser check

Start an isolated fictional demo:

```powershell
$env:RESUMEIQ_DEMO_MODE="true"
$env:RESUMEIQ_DEMO_DATA_DIR="./data/browser-qa"
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8513
```

Verify `http://127.0.0.1:8513/_stcore/health`, then check all four pages at desktop and mobile widths. Confirm that Candidate labels stay anonymous, no contact/filename appears, reveal/correction controls are absent, job-quality blocking and warning states behave correctly, requirement rows are editable, downloads are offered, Settings reports forced anonymous demo mode, and the browser console has no application errors.

For a private-mode correction/reveal check, use only fictional records in a different temporary directory. Do not expose a development server publicly. Azure, managed identity, Entra, private Blob behavior, and a public URL require separate live verification in the user's subscription.
