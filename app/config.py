"""Settings from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    repository: str = os.environ.get("REPOSITORY", "sqlite")  # sqlite | dynamodb
    sqlite_path: str = os.environ.get("SQLITE_PATH", ":memory:")
    table_name: str = os.environ.get("TABLE_NAME", "hospital-quality")
    aws_region: str = os.environ.get("AWS_REGION", "us-east-1")
    seed_file: Path = Path(os.environ.get("SEED_FILE", Path(__file__).resolve().parents[1] / "data" / "hospitals.json"))
    cache_size: int = int(os.environ.get("CACHE_SIZE", "1024"))
    cache_ttl: float = float(os.environ.get("CACHE_TTL_SECONDS", "300"))
    rate_per_second: float = float(os.environ.get("RATE_LIMIT_PER_SECOND", "50"))
    rate_burst: int = int(os.environ.get("RATE_LIMIT_BURST", "100"))
