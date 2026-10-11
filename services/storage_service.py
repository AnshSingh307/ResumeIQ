from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path


class LocalStorageService:
    def __init__(self, upload_dir: str | Path, max_file_mb: int = 10):
        self.upload_dir = Path(upload_dir).resolve()
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_file_mb * 1024 * 1024

    @staticmethod
    def sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def validate(self, file_name: str, data: bytes) -> None:
        extension = Path(file_name).suffix.lower()
        if extension not in {".pdf", ".docx"}:
            raise ValueError("Unsupported file type. Upload a PDF or DOCX file.")
        if not data:
            raise ValueError("The uploaded file is empty.")
        if len(data) > self.max_bytes:
            raise ValueError(f"File exceeds the {self.max_bytes // (1024 * 1024)} MB limit.")
        if extension == ".pdf" and not data.startswith(b"%PDF"):
            raise ValueError("The file extension is PDF, but its content is not a valid PDF signature.")
        if extension == ".docx" and not data.startswith(b"PK"):
            raise ValueError("The file extension is DOCX, but its content is not a valid DOCX container.")

    @staticmethod
    def safe_name(file_name: str) -> str:
        base = Path(file_name).name
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
        return cleaned[:150] or "resume"

    def save(self, file_name: str, data: bytes) -> tuple[Path, str]:
        self.validate(file_name, data)
        digest = self.sha256(data)
        path = (self.upload_dir / f"{digest[:12]}_{self.safe_name(file_name)}").resolve()
        if self.upload_dir not in path.parents:
            raise ValueError("Unsafe upload path was rejected.")
        path.write_bytes(data)
        return path, digest

    def delete_by_hash(self, file_hash: str) -> int:
        removed = 0
        for path in self.upload_dir.glob(f"{file_hash[:12]}_*"):
            resolved = path.resolve()
            if self.upload_dir in resolved.parents and resolved.is_file():
                resolved.unlink()
                removed += 1
        return removed

    def purge_expired(self, retention_days: int) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(0, retention_days))
        removed = 0
        for path in self.upload_dir.iterdir():
            if path.is_file():
                modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                if modified < cutoff:
                    path.unlink()
                    removed += 1
        return removed

