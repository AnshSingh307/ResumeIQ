from __future__ import annotations

from collections import Counter

import pandas as pd
import plotly.express as px
import streamlit as st

from components.ui import empty_state, page_header, privacy_notice
from database.repository import Repository
from models.domain import ProcessingStatus


def render(repository: Repository, anonymous_mode: bool = False) -> None:
    page_header(
        "Recruiter workspace",
        "Dashboard",
        "A clear view of resume processing, requirement coverage, and work that still needs a person.",
        "Anonymous review" if anonymous_mode else "Evidence-led review",
    )
    candidates = repository.list_candidates()
    matches = repository.list_matches()
    statuses = Counter(candidate.processing_status for candidate in candidates)
    analyzed_ids = {match.candidate_id for match in matches}
    review_count = statuses[ProcessingStatus.NEEDS_REVIEW] + statuses[ProcessingStatus.FAILED]
    average_coverage = sum(item.required_coverage for item in matches) / len(matches) if matches else 0

    if anonymous_mode:
        st.info("Identity fields are hidden in review screens and exports until an authorized reviewer deliberately reveals a candidate.")

    metrics = st.columns(4)
    metrics[0].metric("Total resumes", len(candidates))
    metrics[1].metric("Analyzed", len(analyzed_ids))
    metrics[2].metric("Needs attention", review_count)
    metrics[3].metric("Avg. required coverage", f"{average_coverage:.0f}%")

    action, context = st.columns([1, 2.2], vertical_alignment="center")
    with action:
        if st.button("Analyze resumes", type="primary", width="stretch"):
            st.session_state.nav_target = "Resume Analyzer"
            st.rerun()
    with context:
        st.caption("Upload resumes, define one role, and receive evidence-linked results in a single workflow.")

    chart_col, activity_col = st.columns([1.35, 1])
    with chart_col:
        st.subheader("Required-skill coverage")
        if matches:
            frame = pd.DataFrame(
                {
                    "Candidate": [f"Candidate {item.candidate_id}" for item in matches],
                    "Coverage": [item.required_coverage for item in matches],
                }
            )
            figure = px.bar(frame, x="Candidate", y="Coverage", color_discrete_sequence=["#2f6fca"])
            figure.update_layout(
                height=320,
                margin=dict(l=8, r=8, t=8, b=8),
                yaxis_title="Required coverage (%)",
                xaxis_title="",
                showlegend=False,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(figure, width="stretch")
        else:
            empty_state("No analysis yet", "Analyze fictional demo data or upload resumes to populate this chart.")

    with activity_col:
        st.subheader("Recent activity")
        events = repository.list_audit_events(limit=6)
        if events:
            for event in events:
                label = event["event_type"].replace("_", " ").title()
                when = event["created_at"].replace("T", " ")[:16]
                st.markdown(f"**{label}**")
                st.caption(f"{event['entity_type']} · {when} UTC")
        else:
            empty_state("No activity", "Processing and review events will appear here.")

    privacy_notice()
