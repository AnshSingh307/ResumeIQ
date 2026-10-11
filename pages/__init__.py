"""ResumeIQ page renderers. Native Streamlit page navigation is disabled in config."""

"""ResumeIQ's four Streamlit workspace pages."""

from . import candidates, dashboard, resume_analyzer, settings_page

__all__ = ["dashboard", "resume_analyzer", "candidates", "settings_page"]
