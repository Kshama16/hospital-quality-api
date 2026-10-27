"""Domain model and API response schemas."""

from __future__ import annotations

from pydantic import BaseModel

METRICS = {
    # metric name -> True if a higher value is better
    "overall_rating": True,
    "patient_experience_stars": True,
    "sepsis_care_pct": True,
    "ed_median_minutes": False,
    "infection_sir_avg": False,
}


class Hospital(BaseModel):
    provider_id: str
    name: str
    city: str
    state: str
    zip_code: str
    hospital_type: str
    ownership: str
    emergency_services: bool
    overall_rating: int | None = None
    patient_experience_stars: float | None = None
    ed_median_minutes: float | None = None
    sepsis_care_pct: float | None = None
    infection_sir_avg: float | None = None


class HospitalPage(BaseModel):
    items: list[Hospital]
    next_cursor: str | None = None


class SearchResult(BaseModel):
    query: str
    count: int
    items: list[Hospital]


class Ranking(BaseModel):
    state: str | None
    metric: str
    higher_is_better: bool
    items: list[Hospital]
