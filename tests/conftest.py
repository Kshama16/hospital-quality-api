import json
from pathlib import Path

import pytest

from app.models import Hospital

SEED = Path(__file__).resolve().parents[1] / "data" / "hospitals.json"


@pytest.fixture(scope="session")
def all_hospitals() -> list[Hospital]:
    return [Hospital(**r) for r in json.loads(SEED.read_text())]


def make(pid: str, name: str, state: str = "MA", **kw) -> Hospital:
    base = dict(
        provider_id=pid,
        name=name,
        city="Boston",
        state=state,
        zip_code="02114",
        hospital_type="Acute Care Hospitals",
        ownership="Voluntary non-profit - Private",
        emergency_services=True,
    )
    return Hospital(**{**base, **kw})


@pytest.fixture
def sample() -> list[Hospital]:
    return [
        make("220071", "Massachusetts General Hospital", overall_rating=5, ed_median_minutes=288, sepsis_care_pct=49),
        make("220110", "Brigham And Women's Hospital", overall_rating=5, ed_median_minutes=300, sepsis_care_pct=37),
        make("220031", "Boston Medical Center", overall_rating=3, ed_median_minutes=227, sepsis_care_pct=62),
        make("220046", "Berkshire Medical Center", city="Pittsfield", overall_rating=4, ed_median_minutes=254),
        make("330101", "Newyork-Presbyterian Hospital", state="NY", overall_rating=4, ed_median_minutes=310),
    ]
