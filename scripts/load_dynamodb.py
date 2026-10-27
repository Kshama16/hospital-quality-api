"""Loads data/hospitals.json into the deployed DynamoDB table.

Usage: python scripts/load_dynamodb.py <table-name> [region]
"""
import json
import sys
from pathlib import Path

from app.models import Hospital
from app.repositories import DynamoDBHospitalRepository

if __name__ == "__main__":
    table, region = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "us-east-1")
    rows = json.loads((Path(__file__).resolve().parents[1] / "data" / "hospitals.json").read_text())
    n = DynamoDBHospitalRepository(table, region).put_many(Hospital(**r) for r in rows)
    print(f"loaded {n:,} hospitals into {table}")
