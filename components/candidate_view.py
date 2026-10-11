from __future__ import annotations

import json

import streamlit as st

from components.ui import evidence_block, status_label
from models.domain import CandidateProfile, MatchResult, RequirementStatus


def missing_requirements(result: MatchResult) -> list[str]:
    return [item.requirement for item in result.assessments if item.status != RequirementStatus.MATCHED]


def render_result_card(
    candidate: CandidateProfile,
    result: MatchResult,
    *,
    show_contact: bool = False,
    corrected_fields: set[str] | None = None,
    anonymous: bool = False,
) -> None:
    missing = missing_requirements(result)
    with st.expander(f"{candidate.candidate_name} · {result.required_coverage:.0f}% required coverage"):
        badges = []
        if anonymous:
            badges.append("Anonymous review")
        if corrected_fields:
            badges.append(f"Reviewer-corrected fields: {', '.join(sorted(corrected_fields))}")
        if result.requirement_version_id:
            badges.append(f"Requirement snapshot #{result.requirement_version_id}")
        if badges:
            st.caption(" · ".join(badges))
        metrics = st.columns(4)
        metrics[0].metric("Required", f"{result.required_coverage:.0f}%")
        metrics[1].metric("Preferred", f"{result.preferred_coverage:.0f}%")
        metrics[2].metric("Experience evidence", f"{result.experience_coverage:.0f}%")
        metrics[3].metric("Semantic context", f"{result.semantic_similarity:.0f}%")
        if show_contact:
            st.caption(f"{candidate.email or 'No email extracted'} · {candidate.phone or 'No phone extracted'}")
        st.write("**Verified skills**")
        st.write(", ".join(candidate.skills) or "No configured skill evidence found")
        st.write("**Missing or uncertain requirements**")
        st.write(", ".join(missing) or "None in the configured requirements")
        st.divider()
        for assessment in result.assessments:
            st.markdown(f"**{assessment.requirement}** · {status_label(assessment.status)}", unsafe_allow_html=True)
            st.caption(assessment.explanation)
            for evidence in assessment.evidence[:2]:
                evidence_block(evidence.snippet)


def candidate_report(candidate: CandidateProfile, result: MatchResult) -> bytes:
    payload = {
        "notice": "Explainable qualification coverage only. Human verification is required.",
        "candidate": candidate.model_dump(mode="json", exclude={"raw_text"}),
        "analysis": result.model_dump(mode="json"),
    }
    return json.dumps(payload, indent=2).encode("utf-8")
