from __future__ import annotations

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from components.candidate_view import render_result_card
from components.ui import page_header, privacy_notice, step_card
from config.settings import AppConfig
from database.repository import Repository
from models.domain import (
    JobDescription,
    JobRequirement,
    QualitySeverity,
    QualityStatus,
    RequirementCategory,
    RequirementEvaluationMethod,
    RequirementImportance,
)
from services.auth_service import AccessContext
from services.batch_analysis_service import BatchAnalysisService, UploadPayload
from services.privacy_service import PrivacyService
from services.quality_service import JobQualityService
from services.requirement_service import RequirementService
from services.skill_service import SkillService


def requirements_frame(requirements: list[JobRequirement]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Order": item.sort_order + 1,
                "Requirement": item.text,
                "Normalized": item.normalized_value,
                "Category": item.category.value,
                "Importance": item.importance.value,
                "Evaluation": item.evaluation_method.value,
                "Enabled": item.enabled,
                "Notes": item.notes,
                "Source": item.source,
            }
            for item in requirements
        ],
        columns=["Order", "Requirement", "Normalized", "Category", "Importance", "Evaluation", "Enabled", "Notes", "Source"],
    )


def frame_requirements(frame: pd.DataFrame, skills: SkillService) -> list[JobRequirement]:
    rows: list[JobRequirement] = []
    for index, raw in frame.fillna("").to_dict("index").items():
        text = str(raw.get("Requirement", "")).strip()
        if not text:
            continue
        source = str(raw.get("Source", "manual"))
        if source not in {"suggested", "manual", "legacy"}:
            source = "manual"
        try:
            order = max(int(float(raw.get("Order") or len(rows) + 1)) - 1, 0)
        except (TypeError, ValueError):
            order = len(rows)
        rows.append(
            JobRequirement(
                text=text,
                normalized_value=str(raw.get("Normalized", "")).strip() or skills.normalize(text),
                category=RequirementCategory(str(raw.get("Category") or "skill")),
                importance=RequirementImportance(str(raw.get("Importance") or "required")),
                evaluation_method=RequirementEvaluationMethod(str(raw.get("Evaluation") or "resume_evidence")),
                enabled=bool(raw.get("Enabled", True)),
                notes=str(raw.get("Notes", "")).strip(),
                source=source,
                sort_order=order,
            )
        )
    return sorted(rows, key=lambda item: item.sort_order)


def render(
    repository: Repository,
    batch: BatchAnalysisService,
    skill_service: SkillService,
    requirement_service: RequirementService,
    quality_service: JobQualityService,
    privacy: PrivacyService,
    config: AppConfig,
    access: AccessContext,
    anonymous_mode: bool,
) -> None:
    page_header(
        "Three-step analysis",
        "Resume Analyzer",
        "Add resumes, validate job requirements, and review explainable evidence without switching tools.",
        "Anonymous review" if anonymous_mode else ("Fictional demo" if config.demo_mode else "Private workspace"),
    )
    intro = st.columns(3)
    with intro[0]:
        step_card(1, "Add resumes", "PDF or DOCX, processed privately. Multiple files are supported.")
    with intro[1]:
        step_card(2, "Validate the role", "Check wording and confirm an editable requirement version.")
    with intro[2]:
        step_card(3, "Review evidence", "Inspect coverage, excerpts, uncertainty, and manual checks.")

    st.subheader("1. Resumes")
    uploads = []
    demo_candidates = repository.list_candidates() if config.demo_mode else []
    if config.demo_mode:
        st.info(f"Demo mode uses {len(demo_candidates)} bundled fictional candidate(s). Uploads and identity reveal are disabled.")
    else:
        uploads = st.file_uploader(
            "Upload one or more resumes",
            type=["pdf", "docx"],
            accept_multiple_files=True,
            help=f"Maximum {config.max_file_mb} MB per file. Use candidate data only for a lawful recruiting purpose.",
        )

    st.subheader("2. Role and requirement quality")
    saved_jobs = repository.list_jobs()
    options = ["Create a new role"] + [f"#{job.id} · {job.title}" for job in saved_jobs]
    selected_label = st.selectbox("Start from", options, index=1 if config.demo_mode and saved_jobs else 0)
    selected_job = None if selected_label == options[0] else saved_jobs[options.index(selected_label) - 1]
    job_token = str(selected_job.id) if selected_job else "new"

    if st.session_state.get("requirements_job_token") != job_token:
        st.session_state.requirements_job_token = job_token
        st.session_state.requirement_rows = requirements_frame(requirement_service.from_job(selected_job))
        st.session_state.requirement_editor_revision = st.session_state.get("requirement_editor_revision", 0) + 1

    title = st.text_input("Job title", value=selected_job.title if selected_job else "", key=f"job_title_{job_token}")
    description = st.text_area(
        "Job description",
        value=selected_job.description if selected_job else "",
        height=170,
        placeholder="Describe responsibilities and job-related qualifications.",
        key=f"job_description_{job_token}",
    )
    seeds = st.columns(2)
    required_seed = seeds[0].text_area(
        "Required skills to add",
        value=", ".join(selected_job.required_skills if selected_job else []),
        key=f"required_seed_{job_token}",
        help="Comma or line separated. These become editable rows below.",
    )
    preferred_seed = seeds[1].text_area(
        "Preferred skills to add",
        value=", ".join(selected_job.preferred_skills if selected_job else []),
        key=f"preferred_seed_{job_token}",
    )
    minimum_experience = st.number_input(
        "Minimum relevant experience (years)",
        min_value=0.0,
        max_value=50.0,
        step=0.5,
        value=float(selected_job.minimum_experience_years or 0) if selected_job else 0.0,
        key=f"minimum_experience_{job_token}",
    )

    if st.button("Detect and merge suggested requirements", help="Adds recognized skills without overwriting your existing rows."):
        current = frame_requirements(st.session_state.requirement_rows, skill_service)
        suggested = requirement_service.suggest(
            description,
            skill_service.parse_list(required_seed),
            skill_service.parse_list(preferred_seed),
            current,
        )
        st.session_state.requirement_rows = requirements_frame(suggested)
        st.session_state.requirement_editor_revision += 1
        st.rerun()

    st.markdown("**Editable requirement manager**")
    st.caption("Add or delete rows, reorder with Order, disable a row, or mark it required, preferred, manual, or excluded.")
    edited_frame = st.data_editor(
        st.session_state.requirement_rows,
        key=f"requirements_editor_{job_token}_{st.session_state.requirement_editor_revision}",
        width="stretch",
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "Order": st.column_config.NumberColumn(min_value=1, step=1, width="small"),
            "Requirement": st.column_config.TextColumn(required=True, width="large"),
            "Normalized": st.column_config.TextColumn(help="Canonical value used for duplicate detection."),
            "Category": st.column_config.SelectboxColumn(options=[item.value for item in RequirementCategory], required=True),
            "Importance": st.column_config.SelectboxColumn(options=[item.value for item in RequirementImportance], required=True),
            "Evaluation": st.column_config.SelectboxColumn(options=[item.value for item in RequirementEvaluationMethod], required=True),
            "Enabled": st.column_config.CheckboxColumn(),
            "Notes": st.column_config.TextColumn(width="large"),
            "Source": st.column_config.TextColumn(disabled=True),
        },
    )
    st.session_state.requirement_rows = edited_frame
    requirements = frame_requirements(edited_frame, skill_service)
    quality = quality_service.check(
        title,
        description,
        requirements,
        minimum_experience_years=minimum_experience or None,
        actor=access.user_id or access.display_name,
    )

    status_labels = {
        QualityStatus.READY: "Ready",
        QualityStatus.REVIEW: "Review recommended",
        QualityStatus.BLOCKED: "Blocked",
    }
    st.markdown(f"**Quality status: {status_labels[quality.status]}**")
    if not quality.findings:
        st.success("No blocking or warning findings were detected. Human review is still required.")
    for finding in quality.findings:
        message = f"{finding.message} {finding.recommendation}"
        if finding.severity == QualitySeverity.BLOCKING:
            st.error(message)
        elif finding.severity == QualitySeverity.WARNING:
            st.warning(message)
        else:
            st.info(message)
    has_warnings = any(item.severity == QualitySeverity.WARNING for item in quality.findings)
    acknowledge = st.checkbox(
        "I reviewed and accept the non-blocking quality warnings",
        disabled=not has_warnings,
        value=False,
        key=f"ack_quality_{job_token}",
    )
    if selected_job and selected_job.id is not None:
        versions = repository.list_requirement_versions(selected_job.id)
        if versions:
            with st.expander(f"Requirement history · {len(versions)} saved version(s)"):
                for version in versions:
                    st.write(f"**Version {version.version_number}** · {len(version.requirements)} rows · {version.created_at:%Y-%m-%d %H:%M} UTC")
                    st.caption(version.change_summary)

    can_analyze = quality.status != QualityStatus.BLOCKED and (not has_warnings or acknowledge)
    if not config.demo_mode and not uploads:
        can_analyze = False
    if st.button("Analyze candidates", type="primary", width="stretch", disabled=not can_analyze):
        try:
            merged_requirements, merged_count = requirement_service.merge_duplicates(requirements)
            validation_errors = requirement_service.validate(merged_requirements)
            if validation_errors:
                for error in validation_errors:
                    st.error(error)
                return
            job = JobDescription(
                id=selected_job.id if selected_job else None,
                title=title.strip(),
                description=description.strip(),
                minimum_experience_years=minimum_experience or None,
                created_at=selected_job.created_at if selected_job else None,
            ) if selected_job else JobDescription(
                title=title.strip(),
                description=description.strip(),
                minimum_experience_years=minimum_experience or None,
            )
            job = requirement_service.apply_to_job(job, merged_requirements)
            job = batch.save_job(job)
            job, version, created = requirement_service.save_version(
                repository,
                job,
                merged_requirements,
                access.user_id or access.display_name,
            )
            quality_service.save_review(repository, quality, job.id, acknowledge, access)
            progress = st.progress(0, text="Preparing analysis")

            def report(done: int, total: int, message: str) -> None:
                progress.progress(done / max(total, 1), text=message)

            outcome = (
                batch.run_candidates(demo_candidates, job, progress=report)
                if config.demo_mode
                else batch.run_uploads([UploadPayload(item.name, item.getvalue()) for item in uploads], job, progress=report)
            )
            progress.empty()
            st.session_state.last_job_id = outcome.job.id
            st.session_state.last_results = outcome.results
            if merged_count:
                st.info(f"Merged {merged_count} duplicate requirement row(s) before saving.")
            st.toast(f"Analyzed {len(outcome.results)} candidate(s) with requirement version {version.version_number}.", icon="✅")
            st.success("Analysis complete. Review every evidence item before making a recruiting decision.")
            for duplicate in outcome.duplicates:
                st.info(
                    "An uploaded resume already existed, so ResumeIQ reused its candidate record."
                    if anonymous_mode
                    else f"{duplicate} already existed, so ResumeIQ reused the candidate record."
                )
            for error in outcome.errors:
                st.error("A resume could not be processed. Review the server diagnostics without exposing it here." if anonymous_mode else error)
        except ValidationError as exc:
            st.error("Correct the highlighted job or requirement values before analysis.")
            st.caption(str(exc))
        except Exception as exc:
            st.error(
                "Analysis could not finish. Review restricted server diagnostics for details."
                if anonymous_mode
                else f"Analysis could not finish: {exc}"
            )

    results = st.session_state.get("last_results", [])
    if results:
        st.subheader("3. Results")
        if anonymous_mode:
            st.warning("Anonymous review reduces identity exposure, but free-form evidence may still contain identifying context.")
        for candidate, result in results:
            display_candidate = privacy.anonymize_candidate(candidate) if anonymous_mode else candidate
            display_result = privacy.anonymize_match(result, candidate) if anonymous_mode else result
            corrected = {item.field_name for item in repository.list_candidate_corrections(candidate.id) if item.active} if candidate.id else set()
            render_result_card(
                display_candidate,
                display_result,
                show_contact=not anonymous_mode and not config.demo_mode,
                corrected_fields=corrected,
                anonymous=anonymous_mode,
            )
        if st.button("Open Candidates workspace", width="stretch"):
            st.session_state.nav_target = "Candidates"
            st.rerun()
    privacy_notice()
