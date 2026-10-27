"""SQL implementation on SQLite (standard library), with an index on state."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable, Iterator

from app.models import Hospital
from app.repositories.base import HospitalRepository, RepositoryError

FIELDS = list(Hospital.model_fields)
SCHEMA = """
CREATE TABLE IF NOT EXISTS hospital (
    provider_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    zip_code TEXT NOT NULL,
    hospital_type TEXT NOT NULL,
    ownership TEXT NOT NULL,
    emergency_services INTEGER NOT NULL,
    overall_rating INTEGER,
    patient_experience_stars REAL,
    ed_median_minutes REAL,
    sepsis_care_pct REAL,
    infection_sir_avg REAL
);
CREATE INDEX IF NOT EXISTS idx_hospital_state ON hospital (state, provider_id);
"""


class SQLiteHospitalRepository(HospitalRepository):
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)

    def _query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        try:
            with self._lock:
                return self._conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            raise RepositoryError(str(exc)) from exc

    @staticmethod
    def _to_model(row: sqlite3.Row) -> Hospital:
        d = dict(row)
        d["emergency_services"] = bool(d["emergency_services"])
        return Hospital(**d)

    def get(self, provider_id: str) -> Hospital | None:
        rows = self._query("SELECT * FROM hospital WHERE provider_id = ?", (provider_id,))
        return self._to_model(rows[0]) if rows else None

    def list_by_state(self, state: str) -> list[Hospital]:
        rows = self._query("SELECT * FROM hospital WHERE state = ? ORDER BY provider_id", (state,))
        return [self._to_model(r) for r in rows]

    def scan(self) -> Iterator[Hospital]:
        for r in self._query("SELECT * FROM hospital ORDER BY provider_id"):
            yield self._to_model(r)

    def put_many(self, hospitals: Iterable[Hospital]) -> int:
        rows = [tuple(getattr(h, f) for f in FIELDS) for h in hospitals]
        placeholders = ", ".join("?" for _ in FIELDS)
        try:
            with self._lock, self._conn:
                self._conn.executemany(
                    f"INSERT OR REPLACE INTO hospital ({', '.join(FIELDS)}) VALUES ({placeholders})", rows
                )
        except sqlite3.OperationalError as exc:
            raise RepositoryError(str(exc)) from exc
        return len(rows)

    def count(self) -> int:
        return int(self._query("SELECT COUNT(*) FROM hospital")[0][0])
