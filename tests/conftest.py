from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from docx import Document


SAMPLE_TEXT = """Asha Verma
asha.verma@example.com
SUMMARY
Python developer with 3 years of experience.
SKILLS
Python, SQL, Microsoft Azure, Docker
EDUCATION
B.Tech Computer Science
CERTIFICATIONS
Microsoft Certified: Azure Fundamentals
"""


@pytest.fixture
def sample_docx(tmp_path: Path) -> Path:
    path = tmp_path / "sample.docx"
    document = Document()
    for line in SAMPLE_TEXT.splitlines():
        document.add_paragraph(line)
    document.save(path)
    return path


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "sample.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_textbox((50, 50, 550, 780), SAMPLE_TEXT, fontsize=11)
    document.save(path)
    document.close()
    return path

