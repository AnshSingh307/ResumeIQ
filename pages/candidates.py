from __future__ import annotations

import json
from typing import Any, Iterable

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from components.candidate_view import candidate_report, missing_requirements, render_result_card
from components.ui import empty_state, page_header, privacy_notice
from config.settings import AppConfig
from database.repository import Repository
from models.domain import AuditEvent, CandidateProfile, MatchResult
from services.auth_service import AccessContext
from services.correction_service import CORRECTABLE_FIELDS, CandidateCorrectionService
from services.export_service import export_csv, export_excel, results_frame
from services.privacy_service import PrivacyService
from services.workflow_service import ResumeWorkflow


def filter_candidates(
    pairs: Iterable[tuple[CandidateProfile, MatchResult]],
    *,
    search: str = "",
    skills: set[str] | None = None,
    minimum_coverage: float = 0,
    only_missing: bool = False,
    sort_by: str = "Required coverage",
) -> list[tuple[CandidateProfile, MatchResult]]:
    query = search.casefold().strip()
    required_skills = skills or set()
    output = []
    for candidate, result in pairs:
        searchable = " ".join([candidate.candidate_name, candidate.file_name, *candidate.skills]).casefold()
        if query and query not in searchable:
            continue
        if required_skills and not required_skills.issubset(set(candidate.skills)):
            continue
        if result.required_coverage < minimum_coverage:
            continue
        if only_missing and not missing_requirements(result):
            continue
        output.append((candidate, result))
    keys = {
        "Required coverage": lambda pair: pair[1].required_coverage,
        "Newest first": lambda pair: pair[0].created_at.timestamp(),
        "Name A–Z": lambda pair: pair[0].candidate_name.casefold(),
    }
    return sorted(output, key=keys[sort_by], reverse=sort_by != "Name A–Z")


def _display_pair(
    candidate: CandidateProfile,
    result: MatchResult,
    privacy: PrivacyService,
    anonymous: bool,
) -> tuple[CandidateProfile, MatchResult]:
    if not anonymous:
        return candidate, result
    return privacy.anonymize_candidate(candidate), privacy.anonymize_match(result, candidate)


def _editor_value(field_name: str, current: Any, candidate_id: int) -> Any:
    key = f"correction_value_{candidate_id}_{field_name}"
    if field_name == "years_experience":
        use_value = st.checkbox(
            "Candidate has a known experience total",
            value=current is not None,
            key=f"{key}_known",
        )
        value = st.number_input(
            "Corrected years of experience",
            min_value=0.0,
            max_value=80.0,
            value=float(current or 0),
            step=0.5,
            disabled=not use_value,
            key=key,
        )
        return value if use_value else None
    if field_name == "employment_history":
        serialized = json.dumps(
            [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in current],
            indent=2,
        )
        value = st.text_area(
            "Corrected employment history (JSON list)",
            value=serialized,
            height=220,
            key=key,
        )
        parsed = json.loads(value)
        if not isinstance(parsed, list):
            raise ValueError("Employment history must be a JSON list.")
        return parsed
    if field_name in {
        "skills",
        "education",
        "projects",
        "certifications",
        "parse_warnings",
        "reviewer_comments",
    }:
        return [
            item.strip()
            for item in st.text_area(
                "Corrected values (one item per line)",
                value="\n".join(str(item) for item in current),
                height=160,
                key=key,
            ).splitlines()
            if item.strip()
        ]
    value = st.text_input("Corrected value", value=str(current or ""), key=key).strip()
    return value or None if field_name in {"email", "phone"} else value


def _correction_panel(
    candidate: CandidateProfile,
    repository: Repository,
    corrections: CandidateCorrectionService,
    access: AccessContext,
    demo_mode: bool,
) -> None:
    if candidate.id is None:
        return
    st.subheader("Correct extracted data")
    st.caption("Every change needs a reason, keeps the original value, and recalculates current analyses.")
    friendly = {
        "candidate_name": "Candidate name",
        "email": "Email",
        "phone": "Phone",
        "skills": "Skills",
        "education": "Education",
        "employment_history": "Employment history",
        "projects": "Projects",
        "certifications": "Certifications",
        "years_experience": "Years of experience",
        "parse_warnings": "Parsing warnings",
        "reviewer_comments": "Reviewer comments",
    }
    field_name = st.selectbox(
        "Field to correct",
        sorted(CORRECTABLE_FIELDS),
        format_func=lambda item: friendly[item],
        key=f"correction_field_{candidate.id}",
    )
    prior = [item for item in repository.list_candidate_corrections(candidate.id) if item.field_name == field_name]
    original_extracted = prior[-1].original_value if prior else getattr(candidate, field_name)
    st.caption("Original extracted value (retained for audit)")
    st.json(original_extracted, expanded=False)
    try:
        corrected_value = _editor_value(field_name, getattr(candidate, field_name), candidate.id)
        value_error = None
    except (ValueError, json.JSONDecodeError) as exc:
        corrected_value = None
        value_error = str(exc)
        st.error(f"The corrected value is invalid: {exc}")
    reason = st.text_area(
        "Reason for correction",
        placeholder="Example: reviewer confirmed the date range on page 2",
        key=f"correction_reason_{candidate.id}",
    )
    if st.button(
        "Save correction and recalculate",
        type="primary",
        disabled=bool(value_error) or len(reason.strip()) < 3,
        key=f"save_correction_{candidate.id}",
    ):
        try:
            correction, count = corrections.correct(
                candidate.id,
                field_name,
                corrected_value,
                reason,
                access,
                demo_mode,
            )
            st.success(f"Correction #{correction.id} saved. Recalculated {count} current analysis record(s).")
            st.rerun()
        except (PermissionError, ValueError, ValidationError) as exc:
            st.error(f"Correction was not saved: {exc}")

    history = repository.list_candidate_corrections(candidate.id)
    if history:
        with st.expander(f"Correction history · {len(history)} event(s)"):
            for correction in history:
                state = "Active" if correction.active else "Reverted"
                st.markdown(f"**#{correction.id} · {friendly.get(correction.field_name, correction.field_name)} · {state}**")
                st.caption(f"{correction.created_at:%Y-%m-%d %H:%M} UTC · {correction.actor} · {correction.reason}")
                if correction.active:
                    if st.button(
                        "Revert this correction",
                        key=f"revert_correction_{correction.id}",
                    ):
                        try:
                            count = corrections.revert(correction.id, access, demo_mode)
                            st.success(f"Correction reverted. Recalculated {count} current analysis record(s).")
                            st.rerun()
                        except (PermissionError, ValueError) as exc:
                            st.error(str(exc))



def _analysis_history(candidate: CandidateProfile, job_id: int, repository: Repository) -> None:
    if candidate.id is None:
        return
    match_history = repository.list_match_history(candidate.id, job_id)
    if match_history:
        with st.expander(f"Analysis history · {len(match_history)} snapshot(s)"):
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Analyzed at": item.created_at.strftime("%Y-%m-%d %H:%M UTC"),
                            "Requirement snapshot": (
                                f"#{item.requirement_version_id}" if item.requirement_version_id else "Legacy"
                            ),
                            "Required %": item.required_coverage,
                            "Preferred %": item.preferred_coverage,
                            "Experience %": item.experience_coverage,
                        }
                        for item in match_history
                    ]
                ),
                hide_index=True,
                width="stretch",
            )


def render(
    repository: Repository,
    workflow: ResumeWorkflow,
    config: AppConfig,
    access: AccessContext,
    privacy: PrivacyService,
    corrections: CandidateCorrectionService,
    anonymous_mode: bool,
) -> None:
    page_header(
        "Human review workspace",
        "Candidates",
        "Search, compare, correct, export, and inspect the evidence behind each qualification assessment.",
        "Anonymous review" if anonymous_mode else "No automatic rejection",
    )
    if anonymous_mode:
        st.warning(
            "Names, contact details, filenames, and direct identifiers are hidden. Free-form evidence may still contain contextual clues."
        )
    jobs = [job for job in repository.list_jobs() if job.id is not None]
    if not jobs:
        empty_state("No roles yet", "Use Resume Analyzer to define a role and analyze candidates.")
        return
    preferred_job = st.session_state.get("last_job_id")
    default_index = next((index for index, job in enumerate(jobs) if job.id == preferred_job), 0)
    job = st.selectbox("Role", jobs, index=default_index, format_func=lambda item: f"#{item.id} · {item.title}")
    candidates_by_id = {
        candidate.id: candidate for candidate in repository.list_candidates() if candidate.id is not None
    }
    raw_pairs = [
        (candidates_by_id[result.candidate_id], result)
        for result in repository.list_matches(job.id)
        if result.candidate_id in candidates_by_id
    ]
    if not raw_pairs:
        empty_state("No analyzed candidates", "Return to Resume Analyzer and run this role against one or more resumes.")
        return

    revealed_ids = set(st.session_state.get("revealed_candidate_ids", []))
    display_pairs = [
        _display_pair(candidate, result, privacy, anonymous_mode and candidate.id not in revealed_ids)
        for candidate, result in raw_pairs
    ]
    all_skills = sorted({skill for candidate, _ in display_pairs for skill in candidate.skills})
    filter_row = st.columns([1.5, 1.1, 1, 1])
    search = filter_row[0].text_input(
        "Search",
        placeholder="Anonymous label or skill" if anonymous_mode else "Name, file, or skill",
    )
    selected_skills = set(filter_row[1].multiselect("Verified skills", all_skills))
    minimum_coverage = filter_row[2].number_input("Min. required %", 0, 100, 0, 5)
    sort_by = filter_row[3].selectbox("Sort", ["Required coverage", "Newest first", "Name A–Z"])
    only_missing = st.checkbox("Only candidates with missing or uncertain requirements")
    filtered = filter_candidates(
        display_pairs,
        search=search,
        skills=selected_skills,
        minimum_coverage=minimum_coverage,
        only_missing=only_missing,
        sort_by=sort_by,
    )
    if not filtered:
        st.warning("No records match these review filters. This does not mean any candidate was rejected.")
        return

    corrections_by_id = {
        candidate.id: {
            item.field_name
            for item in repository.list_candidate_corrections(candidate.id)
            if item.active
        }
        for candidate, _ in raw_pairs
        if candidate.id is not None
    }
    frame = pd.DataFrame(
        [
            {
                "Candidate": candidate.candidate_name,
                "Required %": result.required_coverage,
                "Preferred %": result.preferred_coverage,
                "Experience evidence %": result.experience_coverage,
                "Missing / uncertain": len(missing_requirements(result)),
                "Reviewer corrected": "Yes" if corrections_by_id.get(candidate.id) else "No",
                "Status": candidate.processing_status.value.replace("_", " ").title(),
            }
            for candidate, result in filtered
        ]
    )
    st.dataframe(frame, width="stretch", hide_index=True)

    st.subheader("Compare")
    labels = {
        f"#{candidate.id} · {candidate.candidate_name}": (candidate, result)
        for candidate, result in filtered
    }
    compare = st.multiselect("Select up to four candidates", labels, max_selections=4)
    if compare:
        columns = st.columns(len(compare))
        for column, label in zip(columns, compare):
            candidate, result = labels[label]
            with column:
                st.markdown(f"**{candidate.candidate_name}**")
                st.metric("Required coverage", f"{result.required_coverage:.0f}%")
                st.caption("Verified skills")
                st.write(", ".join(candidate.skills) or "None detected")
                st.caption("Missing / uncertain")
                st.write(", ".join(missing_requirements(result)) or "None configured")

    st.subheader("Evidence and actions")
    for candidate, result in filtered:
        hidden = anonymous_mode and candidate.id not in revealed_ids
        render_result_card(
            candidate,
            result,
            show_contact=not hidden and not config.demo_mode,
            corrected_fields=corrections_by_id.get(candidate.id, set()),
            anonymous=hidden,
        )

    filtered_ids = {candidate.id for candidate, _ in filtered}
    # Exports remain anonymous while workspace anonymous mode is active, even after an on-screen reveal.
    export_pairs = [
        _display_pair(candidate, result, privacy, anonymous_mode)
        for candidate, result in raw_pairs
        if candidate.id in filtered_ids
    ]
    export_frame = results_frame(
        [result for _, result in export_pairs],
        {candidate.id: candidate for candidate, _ in export_pairs},
        {job.id: job},
    )
    events = repository.list_audit_events(limit=500)
    audit_frame = (
        pd.DataFrame(
            [
                {
                    "event_type": event["event_type"],
                    "entity_type": event["entity_type"],
                    "entity_id": event["entity_id"],
                    "created_at": event["created_at"],
                }
                for event in events
            ]
        )
        if anonymous_mode
        else pd.DataFrame(
            [{**event, "details": json.dumps(event.get("details", {}), sort_keys=True)} for event in events]
        )
    )
    export_cols = st.columns(3)
    export_cols[0].download_button(
        "Download CSV", export_csv(export_frame), f"resumeiq-{job.id}.csv", "text/csv", width="stretch"
    )
    export_cols[1].download_button(
        "Download Excel",
        export_excel(export_frame, audit_frame),
        f"resumeiq-{job.id}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )
    report_label = export_cols[2].selectbox("Candidate report", list(labels), label_visibility="collapsed")
    report_display_candidate, _ = labels[report_label]
    raw_candidate = candidates_by_id[report_display_candidate.id]
    raw_result = next(result for candidate, result in raw_pairs if candidate.id == report_display_candidate.id)
    report_candidate, report_result = _display_pair(raw_candidate, raw_result, privacy, anonymous_mode)
    export_cols[2].download_button(
        "Download selected JSON",
        candidate_report(report_candidate, report_result),
        f"candidate-{report_candidate.id}-report.json",
        "application/json",
        width="stretch",
    )

    review_col, action_col = st.columns(2)
    selected_action = review_col.selectbox("Candidate action", list(labels), key="action_candidate")
    action_display, action_result = labels[selected_action]
    action_candidate = candidates_by_id[action_display.id]
    if review_col.button("Record human review", width="stretch"):
        repository.add_audit_event(
            AuditEvent(
                event_type="human_review_recorded",
                entity_type="match",
                entity_id=action_result.id,
                actor=access.user_id or access.display_name,
                details={"candidate_id": action_candidate.id, "job_id": job.id},
            )
        )
        st.toast("Human review recorded in the audit log.", icon="✅")

    can_reveal = privacy.can_reveal(access, config.demo_mode)
    is_revealed = action_candidate.id in revealed_ids
    if anonymous_mode and not is_revealed:
        if can_reveal:
            if action_col.button("Reveal identity (audit logged)", width="stretch"):
                privacy.reveal_identity(repository, action_candidate.id, job.id, access, config.demo_mode)
                revealed_ids.add(action_candidate.id)
                st.session_state.revealed_candidate_ids = sorted(revealed_ids)
                st.rerun()
        else:
            action_col.info("Identity reveal is unavailable for this access mode.")
    elif anonymous_mode and is_revealed:
        if action_col.button("Hide identity again", width="stretch"):
            revealed_ids.discard(action_candidate.id)
            st.session_state.revealed_candidate_ids = sorted(revealed_ids)
            st.rerun()

    can_correct = corrections.can_correct(access, config.demo_mode)
    if can_correct and (not anonymous_mode or is_revealed):
        with st.expander("Edit extracted information"):
            _correction_panel(
                action_candidate,
                repository,
                corrections,
                access,
                config.demo_mode,
            )
    elif config.demo_mode:
        st.info("Corrections and deletion are disabled in fictional demo mode.")
    elif anonymous_mode and not is_revealed:
        st.caption("Reveal this candidate before editing extracted personal data.")

    _analysis_history(action_candidate, job.id, repository)

    if not config.demo_mode and corrections.can_correct(access, config.demo_mode):
        confirm_key = f"confirm_delete_{action_candidate.id}"
        if not st.session_state.get(confirm_key):
            if st.button("Delete selected candidate…", width="stretch"):
                st.session_state[confirm_key] = True
                st.rerun()
        else:
            st.warning(f"Permanently delete {action_display.candidate_name} and linked analyses?")
            yes, no = st.columns(2)
            if yes.button("Confirm delete", type="primary", width="stretch"):
                workflow.delete(action_candidate)
                st.session_state.pop(confirm_key, None)
                st.rerun()
            if no.button("Cancel", width="stretch"):
                st.session_state.pop(confirm_key, None)
                st.rerun()
    privacy_notice()
