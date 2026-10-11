from __future__ import annotations

import streamlit as st

from components.ui import page_header, privacy_notice
from config.settings import AppConfig
from database.repository import Repository
from services.auth_service import AccessContext
from services.azure_services import all_azure_statuses
from services.storage_service import LocalStorageService


def _saved_bool(repository: Repository, key: str, default: bool) -> bool:
    return (repository.get_setting(key, str(default)) or str(default)).casefold() == "true"


def render(
    repository: Repository,
    config: AppConfig,
    access: AccessContext,
    anonymous_mode: bool = False,
) -> None:
    page_header(
        "Workspace controls",
        "Settings",
        "Configure processing, privacy, retention, theme, and optional Azure integrations.",
        "Read only" if config.demo_mode else "Administrator",
    )
    identity, runtime = st.columns(2)
    with identity:
        st.subheader("Access")
        st.write(f"**Signed in as:** {access.display_name}")
        st.write(f"**Access mode:** {access.mode.replace('_', ' ').title()}")
        st.write(f"**Authentication required:** {'Yes' if config.auth_required else 'No'}")
    with runtime:
        st.subheader("Runtime")
        st.write(f"**Environment:** {config.environment.title()}")
        st.write(f"**Data directory:** `{config.active_data_dir.resolve()}`")
        st.write(f"**Maximum upload:** {config.max_file_mb} MB")

    st.subheader("Processing and appearance")
    disabled = config.demo_mode
    with st.form("settings_form"):
        anonymous_review = st.checkbox(
            "Use anonymous review by default",
            value=True if config.demo_mode else anonymous_mode,
            disabled=disabled,
            help="Hides names, contact details, filenames, and direct identifiers in review views and exports.",
        )
        semantic_provider = st.selectbox(
            "Semantic context provider",
            ["tfidf", "sentence-transformers"],
            index=0
            if (repository.get_setting("semantic_provider", config.semantic_provider) or config.semantic_provider) == "tfidf"
            else 1,
            disabled=disabled,
        )
        theme = st.selectbox(
            "Theme",
            ["light", "dark"],
            index=0 if (repository.get_setting("theme", "light") or "light") == "light" else 1,
            disabled=disabled,
        )
        use_document = st.checkbox(
            "Use Azure Document Intelligence when local extraction fails",
            value=_saved_bool(repository, "use_azure_document_intelligence", config.use_azure_document_intelligence),
            disabled=disabled,
        )
        use_language = st.checkbox(
            "Add Azure AI Language entity extraction",
            value=_saved_bool(repository, "use_azure_language", config.use_azure_language),
            disabled=disabled,
        )
        use_blob = st.checkbox(
            "Copy new source documents to private Azure Blob Storage",
            value=_saved_bool(repository, "use_azure_blob", config.use_azure_blob),
            disabled=disabled,
        )
        retention = st.number_input(
            "Source-document retention days",
            min_value=0,
            max_value=3650,
            value=int(repository.get_setting("retention_days", str(config.retention_days)) or config.retention_days),
            disabled=disabled,
        )
        save = st.form_submit_button("Save settings", type="primary", disabled=disabled)
    if save:
        for key, value in {
            "semantic_provider": semantic_provider,
            "theme": theme,
            "use_azure_document_intelligence": use_document,
            "use_azure_language": use_language,
            "use_azure_blob": use_blob,
            "retention_days": retention,
            "anonymous_review": anonymous_review,
        }.items():
            repository.set_setting(key, str(value))
        st.success("Settings saved.")
        st.rerun()

    if config.demo_mode:
        st.info("Anonymous review is mandatory in demo mode. Identity reveal and reviewer corrections are disabled.")
    else:
        st.caption(
            "Anonymous mode reduces identity exposure; it cannot guarantee perfect de-identification of every free-form sentence. "
            "Authorized identity reveals are explicit and audit logged."
        )

    st.subheader("Retention")
    st.caption("A retention run removes expired local source files. Candidate metadata stays until a reviewer deletes the record.")
    confirm_retention = st.checkbox("I understand this deletes expired source files", disabled=disabled)
    if st.button("Apply retention policy", disabled=disabled or not confirm_retention):
        days = int(repository.get_setting("retention_days", str(config.retention_days)) or config.retention_days)
        removed = LocalStorageService(config.upload_dir, config.max_file_mb).purge_expired(days)
        st.success(f"Retention completed: {removed} expired source file(s) removed.")

    st.subheader("Azure readiness")
    flags = {
        "Azure AI Document Intelligence": use_document,
        "Azure AI Language": use_language,
        "Azure Blob Storage": use_blob,
    }
    for status in all_azure_statuses():
        enabled = flags[status.service]
        icon = "✅" if enabled and status.configured else "⚠️" if enabled else "○"
        st.write(f"{icon} **{status.service}** — {status.message}")
    errors = config.deployment_errors()
    if errors:
        for error in errors:
            st.warning(error)
    else:
        st.success("Runtime settings pass ResumeIQ's deployment guardrails.")
    st.info("Subscription eligibility, regional availability, quota, and pricing must be verified in your own Azure portal.")
    privacy_notice()
