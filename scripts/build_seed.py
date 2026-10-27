"""Builds data/hospitals.json: one record per hospital from public CMS Provider Data.

Usage: python scripts/build_seed.py [RAW_DIR]
RAW_DIR holds the CMS CSVs; if omitted they are downloaded from the CMS metastore.
"""

import json
import ssl
import sys
import tempfile
import urllib.request
from pathlib import Path

import certifi
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATASETS = {
    "xubh-q36u": "hospital_general_information.csv",
    "yv7e-xc69": "timely_and_effective_care.csv",
    "dgck-syfz": "hcahps_patient_survey.csv",
    "77hc-ibv8": "healthcare_associated_infections.csv",
}
METASTORE = "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items/{}"


def download(raw: Path) -> None:
    ctx = ssl.create_default_context(cafile=certifi.where())
    for dataset_id, fname in DATASETS.items():
        with urllib.request.urlopen(METASTORE.format(dataset_id), timeout=60, context=ctx) as resp:
            url = json.load(resp)["distribution"][0]["downloadURL"]
        with urllib.request.urlopen(url, timeout=300, context=ctx) as resp:
            (raw / fname).write_bytes(resp.read())


def num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def main(raw: Path) -> None:
    read = lambda f: pd.read_csv(raw / f, dtype=str)
    gen = read("hospital_general_information.csv")
    timely = read("timely_and_effective_care.csv")
    hcahps = read("hcahps_patient_survey.csv")
    hai = read("healthcare_associated_infections.csv")

    measure = lambda df, mid: df[df["Measure ID"] == mid].set_index("Facility ID")["Score"].pipe(num)
    ed = measure(timely, "OP_18b")
    sepsis = measure(timely, "SEP_1")
    stars = (
        hcahps[hcahps["HCAHPS Measure ID"] == "H_STAR_RATING"]
        .set_index("Facility ID")["Patient Survey Star Rating"]
        .pipe(num)
    )
    sir = (
        hai[hai["Measure ID"].str.endswith("_SIR")]
        .assign(Score=lambda d: num(d["Score"]))
        .groupby("Facility ID")["Score"]
        .mean()
    )

    records = []
    for _, h in gen.iterrows():
        pid = h["Facility ID"]

        def val(s: pd.Series, pid: str = pid) -> float | None:
            return None if pid not in s.index or pd.isna(s[pid]) else round(float(s[pid]), 3)

        rating = num(pd.Series([h["Hospital overall rating"]]))[0]
        records.append(
            {
                "provider_id": pid,
                "name": h["Facility Name"].title(),
                "city": h["City/Town"].title(),
                "state": h["State"],
                "zip_code": h["ZIP Code"],
                "hospital_type": h["Hospital Type"],
                "ownership": h["Hospital Ownership"],
                "emergency_services": h["Emergency Services"] == "Yes",
                "overall_rating": None if pd.isna(rating) else int(rating),
                "patient_experience_stars": val(stars),
                "ed_median_minutes": val(ed),
                "sepsis_care_pct": val(sepsis),
                "infection_sir_avg": val(sir),
            }
        )
    out = ROOT / "data" / "hospitals.json"
    out.write_text(json.dumps(records, separators=(",", ":")))
    print(f"{out}: {len(records):,} hospitals")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main(Path(sys.argv[1]))
    else:
        with tempfile.TemporaryDirectory() as tmp:
            download(Path(tmp))
            main(Path(tmp))
