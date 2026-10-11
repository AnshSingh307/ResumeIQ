from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any

from models.domain import (
    AuditEvent,
    CandidateCorrection,
    CandidateProfile,
    JobDescription,
    JobRequirementVersion,
    MatchResult,
    QualityCheckResult,
)


class Repository:
    """Small SQLite repository. JSON stores validated Pydantic payloads for easy evolution."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            file_hash TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            candidate_name TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            job_id INTEGER NOT NULL,
            composite_indicator REAL NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(candidate_id, job_id),
            FOREIGN KEY(candidate_id) REFERENCES candidates(id) ON DELETE CASCADE,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER,
            actor TEXT NOT NULL,
            details TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS candidate_corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            field_name TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(candidate_id) REFERENCES candidates(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS job_requirement_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            version_number INTEGER NOT NULL,
            payload TEXT NOT NULL,
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(job_id, version_number),
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS quality_check_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            status TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS match_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            job_id INTEGER NOT NULL,
            requirement_version_id INTEGER,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(candidate_id) REFERENCES candidates(id) ON DELETE CASCADE,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_corrections_candidate ON candidate_corrections(candidate_id, id DESC);
        CREATE INDEX IF NOT EXISTS idx_versions_job ON job_requirement_versions(job_id, version_number DESC);
        CREATE INDEX IF NOT EXISTS idx_match_history_pair ON match_history(candidate_id, job_id, id DESC);
        """
        with self.connect() as connection:
            connection.executescript(schema)

    @staticmethod
    def _json(model: Any) -> str:
        return model.model_dump_json()

    def add_candidate(self, candidate: CandidateProfile) -> CandidateProfile:
        payload = self._json(candidate)
        with self._lock, self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO candidates(file_name,file_hash,status,candidate_name,payload,created_at) VALUES(?,?,?,?,?,?)",
                (
                    candidate.file_name,
                    candidate.file_hash,
                    candidate.processing_status.value,
                    candidate.candidate_name,
                    payload,
                    candidate.created_at.isoformat(),
                ),
            )
            candidate.id = int(cursor.lastrowid)
            connection.execute("UPDATE candidates SET payload=? WHERE id=?", (self._json(candidate), candidate.id))
        return candidate

    def find_candidate_by_hash(self, file_hash: str) -> CandidateProfile | None:
        with self.connect() as connection:
            row = connection.execute("SELECT payload FROM candidates WHERE file_hash=?", (file_hash,)).fetchone()
        return CandidateProfile.model_validate_json(row["payload"]) if row else None

    def update_candidate(self, candidate: CandidateProfile) -> CandidateProfile:
        if candidate.id is None:
            raise ValueError("A saved candidate must have an id before it can be updated.")
        with self._lock, self.connect() as connection:
            connection.execute(
                "UPDATE candidates SET file_name=?, status=?, candidate_name=?, payload=? WHERE id=?",
                (
                    candidate.file_name,
                    candidate.processing_status.value,
                    candidate.candidate_name,
                    self._json(candidate),
                    candidate.id,
                ),
            )
        return candidate

    def get_candidate(self, candidate_id: int) -> CandidateProfile | None:
        with self.connect() as connection:
            row = connection.execute("SELECT payload FROM candidates WHERE id=?", (candidate_id,)).fetchone()
        return CandidateProfile.model_validate_json(row["payload"]) if row else None

    def list_candidates(self) -> list[CandidateProfile]:
        with self.connect() as connection:
            rows = connection.execute("SELECT payload FROM candidates ORDER BY id DESC").fetchall()
        return [CandidateProfile.model_validate_json(row["payload"]) for row in rows]

    def delete_candidate(self, candidate_id: int) -> None:
        with self._lock, self.connect() as connection:
            connection.execute("DELETE FROM candidates WHERE id=?", (candidate_id,))

    def add_job(self, job: JobDescription) -> JobDescription:
        with self._lock, self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO jobs(title,payload,created_at) VALUES(?,?,?)",
                (job.title, self._json(job), job.created_at.isoformat()),
            )
            job.id = int(cursor.lastrowid)
            connection.execute("UPDATE jobs SET payload=? WHERE id=?", (self._json(job), job.id))
        return job

    def update_job(self, job: JobDescription) -> JobDescription:
        if job.id is None:
            raise ValueError("A saved job must have an id before it can be updated.")
        with self._lock, self.connect() as connection:
            connection.execute("UPDATE jobs SET title=?, payload=? WHERE id=?", (job.title, self._json(job), job.id))
        return job

    def get_job(self, job_id: int) -> JobDescription | None:
        with self.connect() as connection:
            row = connection.execute("SELECT payload FROM jobs WHERE id=?", (job_id,)).fetchone()
        return JobDescription.model_validate_json(row["payload"]) if row else None

    def list_jobs(self) -> list[JobDescription]:
        with self.connect() as connection:
            rows = connection.execute("SELECT payload FROM jobs ORDER BY id DESC").fetchall()
        return [JobDescription.model_validate_json(row["payload"]) for row in rows]

    def save_match(self, result: MatchResult) -> MatchResult:
        with self._lock, self.connect() as connection:
            connection.execute(
                """
                INSERT INTO matches(candidate_id,job_id,composite_indicator,payload,created_at)
                VALUES(?,?,?,?,?)
                ON CONFLICT(candidate_id,job_id) DO UPDATE SET
                    composite_indicator=excluded.composite_indicator,
                    payload=excluded.payload,
                    created_at=excluded.created_at
                """,
                (
                    result.candidate_id,
                    result.job_id,
                    result.composite_indicator,
                    self._json(result),
                    result.created_at.isoformat(),
                ),
            )
            row = connection.execute(
                "SELECT id FROM matches WHERE candidate_id=? AND job_id=?", (result.candidate_id, result.job_id)
            ).fetchone()
            result.id = int(row["id"])
            connection.execute("UPDATE matches SET payload=? WHERE id=?", (self._json(result), result.id))
            connection.execute(
                """
                INSERT INTO match_history(candidate_id,job_id,requirement_version_id,payload,created_at)
                VALUES(?,?,?,?,?)
                """,
                (
                    result.candidate_id,
                    result.job_id,
                    result.requirement_version_id,
                    self._json(result),
                    result.created_at.isoformat(),
                ),
            )
        return result

    def get_match(self, candidate_id: int, job_id: int) -> MatchResult | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM matches WHERE candidate_id=? AND job_id=?", (candidate_id, job_id)
            ).fetchone()
        return MatchResult.model_validate_json(row["payload"]) if row else None

    def list_matches(self, job_id: int | None = None) -> list[MatchResult]:
        query = "SELECT payload FROM matches"
        params: tuple[int, ...] = ()
        if job_id is not None:
            query += " WHERE job_id=?"
            params = (job_id,)
        query += " ORDER BY composite_indicator DESC"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [MatchResult.model_validate_json(row["payload"]) for row in rows]

    def list_match_history(self, candidate_id: int, job_id: int) -> list[MatchResult]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM match_history WHERE candidate_id=? AND job_id=? ORDER BY id DESC",
                (candidate_id, job_id),
            ).fetchall()
        return [MatchResult.model_validate_json(row["payload"]) for row in rows]

    def add_correction(self, correction: CandidateCorrection) -> CandidateCorrection:
        with self._lock, self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO candidate_corrections(candidate_id,field_name,payload,created_at) VALUES(?,?,?,?)",
                (
                    correction.candidate_id,
                    correction.field_name,
                    self._json(correction),
                    correction.created_at.isoformat(),
                ),
            )
            correction.id = int(cursor.lastrowid)
            connection.execute(
                "UPDATE candidate_corrections SET payload=? WHERE id=?",
                (self._json(correction), correction.id),
            )
        return correction

    def update_correction(self, correction: CandidateCorrection) -> CandidateCorrection:
        if correction.id is None:
            raise ValueError("A correction must have an id before it can be updated.")
        with self._lock, self.connect() as connection:
            connection.execute(
                "UPDATE candidate_corrections SET payload=? WHERE id=?",
                (self._json(correction), correction.id),
            )
        return correction

    def get_correction(self, correction_id: int) -> CandidateCorrection | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM candidate_corrections WHERE id=?", (correction_id,)
            ).fetchone()
        return CandidateCorrection.model_validate_json(row["payload"]) if row else None

    def list_candidate_corrections(self, candidate_id: int) -> list[CandidateCorrection]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM candidate_corrections WHERE candidate_id=? ORDER BY id DESC",
                (candidate_id,),
            ).fetchall()
        return [CandidateCorrection.model_validate_json(row["payload"]) for row in rows]

    def add_requirement_version(self, version: JobRequirementVersion) -> JobRequirementVersion:
        with self._lock, self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO job_requirement_versions(job_id,version_number,payload,actor,created_at)
                VALUES(?,?,?,?,?)
                """,
                (
                    version.job_id,
                    version.version_number,
                    self._json(version),
                    version.actor,
                    version.created_at.isoformat(),
                ),
            )
            version.id = int(cursor.lastrowid)
            connection.execute(
                "UPDATE job_requirement_versions SET payload=? WHERE id=?",
                (self._json(version), version.id),
            )
        return version

    def list_requirement_versions(self, job_id: int) -> list[JobRequirementVersion]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM job_requirement_versions WHERE job_id=? ORDER BY version_number DESC",
                (job_id,),
            ).fetchall()
        return [JobRequirementVersion.model_validate_json(row["payload"]) for row in rows]

    def latest_requirement_version(self, job_id: int) -> JobRequirementVersion | None:
        versions = self.list_requirement_versions(job_id)
        return versions[0] if versions else None

    def add_quality_check(self, result: QualityCheckResult) -> QualityCheckResult:
        with self._lock, self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO quality_check_results(job_id,status,payload,created_at) VALUES(?,?,?,?)",
                (result.job_id, result.status.value, self._json(result), result.created_at.isoformat()),
            )
            result.id = int(cursor.lastrowid)
            connection.execute(
                "UPDATE quality_check_results SET payload=? WHERE id=?", (self._json(result), result.id)
            )
        return result

    def add_audit_event(self, event: AuditEvent) -> AuditEvent:
        with self._lock, self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO audit_events(event_type,entity_type,entity_id,actor,details,created_at) VALUES(?,?,?,?,?,?)",
                (
                    event.event_type,
                    event.entity_type,
                    event.entity_id,
                    event.actor,
                    json.dumps(event.details),
                    event.created_at.isoformat(),
                ),
            )
            event.id = int(cursor.lastrowid)
        return event

    def list_audit_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{**dict(row), "details": json.loads(row["details"])} for row in rows]

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self.connect() as connection:
            row = connection.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

