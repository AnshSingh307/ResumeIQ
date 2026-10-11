from __future__ import annotations

import streamlit as st

from components.ui import apply_theme, brand, footer
from config.settings import get_config
from database.repository import Repository
from pages import candidates, dashboard, resume_analyzer, settings_page
from services.auth_service import resolve_access
from services.batch_analysis_service import BatchAnalysisService
from services.correction_service import CandidateCorrectionService
from services.demo_service import seed_demo_data
from services.matching_service import MatchingService
from services.privacy_service import PrivacyService
from services.quality_service import JobQualityService
from services.requirement_service import RequirementService
from services.skill_service import SemanticSimilarityService, SkillService
from services.workflow_service import ResumeWorkflow


st.set_page_config(
    page_title="ResumeIQ · Intelligent Resume Insights",
    page_icon="RI",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def application_services():
    config = get_config()
    repository = Repository(config.database_path)
    skills = SkillService()
    workflow = ResumeWorkflow(config, repository)
    return config, repository, skills, workflow


@st.cache_resource
def matching_service(provider: str, sentence_model: str):
    return MatchingService(SkillService(), SemanticSimilarityService(provider, sentence_model))


def saved_bool(repository: Repository, key: str, default: bool) -> bool:
    return (repository.get_setting(key, str(default)) or str(default)).casefold() == "true"


def request_headers() -> dict[str, str]:
    try:
        return {str(key): str(value) for key, value in st.context.headers.items()}
    except Exception:
        return {}


config, repository, skills, workflow = application_services()
theme = repository.get_setting("theme", "light") or "light"
apply_theme(theme)

deployment_errors = config.deployment_errors()
for problem in deployment_errors:
    st.error(problem)
if deployment_errors:
    st.stop()

access = resolve_access(config, request_headers())
if not access.authenticated:
    st.title("ResumeIQ")
    st.error(access.reason or "Access is not authorized.")
    st.link_button("Sign in with Microsoft", "/.auth/login/aad?post_login_redirect_uri=/")
    st.stop()

if config.demo_mode:
    config.use_azure_document_intelligence = False
    config.use_azure_language = False
    config.use_azure_blob = False
else:
    config.use_azure_document_intelligence = saved_bool(
        repository, "use_azure_document_intelligence", config.use_azure_document_intelligence
    )
    config.use_azure_language = saved_bool(repository, "use_azure_language", config.use_azure_language)
    config.use_azure_blob = saved_bool(repository, "use_azure_blob", config.use_azure_blob)

semantic_provider = repository.get_setting("semantic_provider", config.semantic_provider) or config.semantic_provider
matcher = matching_service(semantic_provider, config.sentence_model)
actor = access.user_id or access.display_name
workflow.actor = actor
batch = BatchAnalysisService(repository, workflow, matcher, actor=actor)
privacy = PrivacyService()
requirement_service = RequirementService(skills)
quality_service = JobQualityService(skills)
correction_service = CandidateCorrectionService(repository, matcher)
anonymous_mode = config.anonymous_review_enabled(
    saved_bool(repository, "anonymous_review", config.anonymous_default)
)
if config.demo_mode:
    seed_demo_data(repository, batch)

navigation_items = ["Dashboard", "Resume Analyzer", "Candidates", "Settings"]
icons = {"Dashboard": "▦", "Resume Analyzer": "◎", "Candidates": "◉", "Settings": "⚙"}
if st.session_state.get("nav_target") in navigation_items:
    st.session_state.nav = st.session_state.pop("nav_target")
if st.session_state.get("nav") not in navigation_items:
    st.session_state.nav = "Dashboard"

with st.sidebar:
    brand()
    navigation = st.radio(
        "Workspace",
        navigation_items,
        index=navigation_items.index(st.session_state.nav),
        key=f"nav_selector_{st.session_state.nav}",
        format_func=lambda item: f"{icons[item]}  {item}",
        label_visibility="collapsed",
    )
    st.divider()
    st.caption(access.display_name)
    st.caption("Fictional protected demo" if config.demo_mode else "Private recruiter workspace")
    if anonymous_mode:
        st.caption("Anonymous review active")

st.session_state.nav = navigation

if navigation == "Dashboard":
    dashboard.render(repository, anonymous_mode)
elif navigation == "Resume Analyzer":
    resume_analyzer.render(
        repository,
        batch,
        skills,
        requirement_service,
        quality_service,
        privacy,
        config,
        access,
        anonymous_mode,
    )
elif navigation == "Candidates":
    candidates.render(
        repository,
        workflow,
        config,
        access,
        privacy,
        correction_service,
        anonymous_mode,
    )
else:
    settings_page.render(repository, config, access, anonymous_mode)

footer(config.environment, config.demo_mode)
