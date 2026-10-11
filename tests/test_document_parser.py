from pathlib import Path

import pytest

from services.document_parser import DocumentParseError, DocumentParser


def test_pdf_extraction(sample_pdf: Path) -> None:
    assert "Python developer" in DocumentParser().extract(sample_pdf)


def test_docx_extraction(sample_docx: Path) -> None:
    assert "Microsoft Azure" in DocumentParser().extract(sample_docx)


def test_corrupt_pdf_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-this-is-not-a-document")
    with pytest.raises(DocumentParseError):
        DocumentParser().extract(path)

