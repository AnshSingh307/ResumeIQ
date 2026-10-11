from __future__ import annotations

from io import BytesIO, StringIO

import pandas as pd

from models.domain import CandidateProfile, JobDescription, MatchResult


def results_frame(
    matches: list[MatchResult], candidates: dict[int, CandidateProfile], jobs: dict[int, JobDescription]
) -> pd.DataFrame:
    rows = []
    for match in matches:
        candidate = candidates.get(match.candidate_id)
        job = jobs.get(match.job_id)
        rows.append(
            {
                "candidate_id": match.candidate_id,
                "candidate_name": candidate.candidate_name if candidate else "Unknown",
                "file_name": candidate.file_name if candidate else "Unknown",
                "job_id": match.job_id,
                "job_title": job.title if job else "Unknown",
                "required_skill_coverage_percent": match.required_coverage,
                "preferred_skill_coverage_percent": match.preferred_coverage,
                "experience_evidence_coverage_percent": match.experience_coverage,
                "certification_coverage_percent": match.certification_coverage,
                "semantic_similarity_percent": match.semantic_similarity,
                "composite_screening_indicator_percent": match.composite_indicator,
                "human_review_required": True,
            }
        )
    return pd.DataFrame(rows)


def export_csv(frame: pd.DataFrame) -> bytes:
    buffer = StringIO()
    frame.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8-sig")


def export_excel(frame: pd.DataFrame, audit_frame: pd.DataFrame | None = None) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="Match results", index=False)
        if audit_frame is not None:
            audit_frame.to_excel(writer, sheet_name="Review audit", index=False)
        workbook = writer.book
        for sheet in workbook.worksheets:
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for column_cells in sheet.columns:
                width = min(max(len(str(cell.value or "")) for cell in column_cells) + 2, 48)
                sheet.column_dimensions[column_cells[0].column_letter].width = width
    return buffer.getvalue()

