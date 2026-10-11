from __future__ import annotations

import html

import streamlit as st

from models.domain import RequirementStatus


def _theme_css(theme: str) -> str:
    if theme == "dark":
        return """
        :root { --ri-bg:#081120; --ri-panel:#101c2f; --ri-panel-2:#14243b; --ri-text:#eef4ff;
            --ri-muted:#9eacc2; --ri-border:#243753; --ri-soft:#132b4d; --ri-navy:#07152e; }
        """
    return """
        :root { --ri-bg:#f5f7fb; --ri-panel:#ffffff; --ri-panel-2:#f8fafc; --ri-text:#12213a;
            --ri-muted:#607089; --ri-border:#dce4ef; --ri-soft:#eaf2ff; --ri-navy:#071b3a; }
    """


def apply_theme(theme: str = "light") -> None:
    st.markdown(
        f"""
<style>
    {_theme_css(theme)}
    .stApp {{ background: var(--ri-bg); color:var(--ri-text); }}
    .block-container {{ max-width: 1260px; padding-top: 1.7rem; padding-bottom: 2.5rem; }}
    [data-testid="stSidebar"] {{ background: var(--ri-navy); border-right:0; }}
    [data-testid="stSidebar"] * {{ color:#dce8fb; }}
    [data-testid="stSidebar"] [role="radiogroup"] label {{ border-radius:11px; padding:.48rem .65rem; transition:background .16s ease, transform .16s ease; }}
    [data-testid="stSidebar"] [role="radiogroup"] label:hover {{ background:rgba(255,255,255,.08); transform:translateX(2px); }}
    [data-testid="stSidebar"] [aria-checked="true"] {{ background:#173f75 !important; }}
    .ri-brand-row {{ display:flex; align-items:center; gap:.7rem; margin:.2rem 0 .25rem; }}
    .ri-logo {{ display:flex; align-items:center; justify-content:center; width:36px; height:36px; border-radius:11px; color:#071b3a; background:#7db4ff; font-weight:900; font-size:1.05rem; box-shadow:0 8px 22px rgba(60,130,220,.25); }}
    .ri-brand {{ font-size:1.32rem; font-weight:800; letter-spacing:-.035em; color:white; }}
    .ri-tagline {{ color:#9fb1ca; font-size:.82rem; margin:0 0 1.2rem 2.9rem; }}
    .ri-header {{ display:flex; justify-content:space-between; align-items:flex-start; gap:1rem; margin-bottom:1.2rem; }}
    .ri-kicker {{ color:#2f6fca; font-size:.73rem; font-weight:800; letter-spacing:.13em; text-transform:uppercase; }}
    .ri-title {{ color:var(--ri-text); font-size:2.05rem; line-height:1.08; font-weight:800; letter-spacing:-.04em; margin:.2rem 0 .38rem; }}
    .ri-subtitle {{ color:var(--ri-muted); max-width:780px; line-height:1.55; }}
    .ri-badge {{ display:inline-flex; align-items:center; gap:.35rem; border:1px solid var(--ri-border); background:var(--ri-panel); color:var(--ri-muted); padding:.42rem .65rem; border-radius:999px; font-size:.76rem; font-weight:700; white-space:nowrap; }}
    .ri-dot {{ width:7px; height:7px; border-radius:50%; background:#22a06b; }}
    .ri-card {{ background:var(--ri-panel); border:1px solid var(--ri-border); border-radius:16px; padding:1rem 1.1rem; box-shadow:0 8px 26px rgba(19,41,75,.055); margin-bottom:.8rem; }}
    .ri-card-title {{ color:var(--ri-text); font-size:.83rem; font-weight:800; margin-bottom:.22rem; }}
    .ri-card-copy {{ color:var(--ri-muted); font-size:.86rem; line-height:1.5; }}
    .ri-step {{ color:#2f6fca; font-weight:800; font-size:.74rem; letter-spacing:.08em; }}
    .ri-evidence {{ background:var(--ri-soft); border-left:3px solid #4f8bd9; border-radius:8px; padding:.7rem .82rem; color:var(--ri-text); margin:.42rem 0; font-size:.88rem; line-height:1.45; }}
    .ri-privacy {{ background:var(--ri-soft); border:1px solid #b9d2f4; color:var(--ri-text); border-radius:13px; padding:.82rem .95rem; font-size:.86rem; line-height:1.45; margin-top:1rem; }}
    .ri-empty {{ text-align:center; background:var(--ri-panel); border:1px dashed #b9c6d9; border-radius:16px; padding:2rem 1rem; color:var(--ri-muted); }}
    .ri-footer {{ color:var(--ri-muted); font-size:.74rem; border-top:1px solid var(--ri-border); margin-top:2rem; padding-top:1rem; }}
    .status-matched {{ color:#18794e; font-weight:750; }}
    .status-not_found {{ color:#c23b3b; font-weight:750; }}
    .status-uncertain, .status-manual_verification {{ color:#a15c00; font-weight:750; }}
    [data-testid="stMetric"] {{ background:var(--ri-panel); border:1px solid var(--ri-border); padding:.95rem 1rem; border-radius:15px; box-shadow:0 7px 24px rgba(19,41,75,.05); }}
    [data-testid="stMetricLabel"] {{ color:var(--ri-muted); }}
    [data-testid="stMetricValue"] {{ color:var(--ri-text); letter-spacing:-.03em; }}
    .stButton > button, .stDownloadButton > button {{ border-radius:10px; font-weight:700; min-height:2.55rem; transition:transform .14s ease, box-shadow .14s ease; }}
    .stButton > button:hover, .stDownloadButton > button:hover {{ transform:translateY(-1px); box-shadow:0 7px 18px rgba(30,79,140,.12); }}
    [data-testid="stFileUploaderDropzone"] {{ background:var(--ri-panel-2); border:1px dashed #9db0c8; border-radius:14px; }}
    [data-testid="stDataFrame"] {{ border:1px solid var(--ri-border); border-radius:13px; overflow:hidden; }}
    [data-testid="stExpander"] {{ background:var(--ri-panel); border-color:var(--ri-border); border-radius:12px; }}
    div[data-baseweb="select"] > div, .stTextInput input, .stTextArea textarea {{ border-color:var(--ri-border); border-radius:10px; }}
    @media (max-width: 760px) {{
        .block-container {{ padding:1rem .85rem 2rem; }}
        .ri-title {{ font-size:1.65rem; }}
        .ri-header {{ display:block; }}
        .ri-badge {{ margin-top:.7rem; }}
        [data-testid="stHorizontalBlock"] {{ gap:.6rem; }}
    }}
</style>
        """,
        unsafe_allow_html=True,
    )


def brand() -> None:
    st.markdown(
        '<div class="ri-brand-row"><div class="ri-logo">RI</div><div class="ri-brand">ResumeIQ</div></div>'
        '<div class="ri-tagline">Intelligent Resume Insights</div>',
        unsafe_allow_html=True,
    )


def page_header(kicker: str, title: str, subtitle: str, badge: str | None = None) -> None:
    badge_html = f'<div class="ri-badge"><span class="ri-dot"></span>{html.escape(badge)}</div>' if badge else ""
    st.markdown(
        '<div class="ri-header"><div>'
        f'<div class="ri-kicker">{html.escape(kicker)}</div>'
        f'<div class="ri-title">{html.escape(title)}</div>'
        f'<div class="ri-subtitle">{html.escape(subtitle)}</div>'
        f'</div>{badge_html}</div>',
        unsafe_allow_html=True,
    )


def step_card(number: int, title: str, copy: str) -> None:
    st.markdown(
        f'<div class="ri-card"><div class="ri-step">STEP {number}</div>'
        f'<div class="ri-card-title">{html.escape(title)}</div>'
        f'<div class="ri-card-copy">{html.escape(copy)}</div></div>',
        unsafe_allow_html=True,
    )


def empty_state(title: str, copy: str) -> None:
    st.markdown(f'<div class="ri-empty"><strong>{html.escape(title)}</strong><br>{html.escape(copy)}</div>', unsafe_allow_html=True)


def privacy_notice() -> None:
    st.markdown(
        '<div class="ri-privacy"><strong>Human review required.</strong> Coverage values describe evidence found '
        'against explicit requirements. They do not predict job performance, automatically reject applicants, or '
        'use protected characteristics. Verify every uncertain or missing item against the source resume.</div>',
        unsafe_allow_html=True,
    )


def evidence_block(snippet: str) -> None:
    st.markdown(f'<div class="ri-evidence">“{html.escape(snippet)}”</div>', unsafe_allow_html=True)


def status_label(status: RequirementStatus) -> str:
    labels = {RequirementStatus.MATCHED: "Matched", RequirementStatus.NOT_FOUND: "Not found", RequirementStatus.UNCERTAIN: "Uncertain", RequirementStatus.MANUAL_VERIFY: "Manual verification"}
    return f'<span class="status-{status.value}">{labels[status]}</span>'


def footer(environment: str, demo_mode: bool) -> None:
    mode = "Fictional public demo" if demo_mode else ("Production" if environment == "production" else "Local development")
    st.markdown(
        f'<div class="ri-footer">ResumeIQ · Intelligent Resume Insights · {html.escape(mode)} · '
        'Explainable screening support, never an automated hiring decision.</div>',
        unsafe_allow_html=True,
    )

