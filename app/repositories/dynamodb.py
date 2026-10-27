"""NoSQL implementation on Amazon DynamoDB.

Table design (single table):
  PK = "HOSPITAL#<provider_id>", SK = "PROFILE"     -> get by ID: one GetItem
  GSI "state-index": state (partition) + provider_id (sort) -> hospitals in a state: one Query
Numbers are stored as Decimal, as DynamoDB requires.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from decimal import Decimal
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.models import Hospital
from app.repositories.base import HospitalRepository, RepositoryError

STATE_INDEX = "state-index"


def table_definition(name: str) -> dict[str, Any]:
    """CreateTable arguments; the SAM template in infra/ defines the same table."""
    return dict(
        TableName=name,
        BillingMode="PAY_PER_REQUEST",
        KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
        AttributeDefinitions=[{"AttributeName": a, "AttributeType": "S"} for a in ("PK", "SK", "state", "provider_id")],
        GlobalSecondaryIndexes=[
            {
                "IndexName": STATE_INDEX,
                "KeySchema": [
                    {"AttributeName": "state", "KeyType": "HASH"},
                    {"AttributeName": "provider_id", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    )


def _to_item(h: Hospital) -> dict[str, Any]:
    item: dict[str, Any] = {"PK": f"HOSPITAL#{h.provider_id}", "SK": "PROFILE"}
    for k, v in h.model_dump().items():
        if v is None:
            continue  # DynamoDB items omit missing attributes
        item[k] = Decimal(str(v)) if isinstance(v, float) else v
    return item


def _to_model(item: dict[str, Any]) -> Hospital:
    d = {k: v for k, v in item.items() if k not in ("PK", "SK")}
    for k, v in d.items():
        if isinstance(v, Decimal):
            d[k] = int(v) if k == "overall_rating" else float(v)
    return Hospital(**d)


class DynamoDBHospitalRepository(HospitalRepository):
    def __init__(self, table_name: str, region: str = "us-east-1", resource: Any = None) -> None:
        self._table = (resource or boto3.resource("dynamodb", region_name=region)).Table(table_name)

    def _call(self, fn: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return fn(**kwargs)
        except (ClientError, BotoCoreError) as exc:
            raise RepositoryError(str(exc)) from exc

    def get(self, provider_id: str) -> Hospital | None:
        resp = self._call(self._table.get_item, Key={"PK": f"HOSPITAL#{provider_id}", "SK": "PROFILE"})
        return _to_model(resp["Item"]) if "Item" in resp else None

    def _paginate(self, fn: Any, **kwargs: Any) -> Iterator[dict[str, Any]]:
        """Follows LastEvaluatedKey until DynamoDB has returned every page."""
        while True:
            resp = self._call(fn, **kwargs)
            yield from resp.get("Items", [])
            if "LastEvaluatedKey" not in resp:
                return
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    def list_by_state(self, state: str) -> list[Hospital]:
        from boto3.dynamodb.conditions import Key

        items = self._paginate(self._table.query, IndexName=STATE_INDEX, KeyConditionExpression=Key("state").eq(state))
        return [_to_model(i) for i in items]

    def scan(self) -> Iterator[Hospital]:
        for item in self._paginate(self._table.scan):
            yield _to_model(item)

    def put_many(self, hospitals: Iterable[Hospital]) -> int:
        n = 0
        try:
            with self._table.batch_writer() as batch:  # batches of 25, retries unprocessed items
                for h in hospitals:
                    batch.put_item(Item=_to_item(h))
                    n += 1
        except (ClientError, BotoCoreError) as exc:
            raise RepositoryError(str(exc)) from exc
        return n

    def count(self) -> int:
        total, kwargs = 0, {"Select": "COUNT"}
        while True:
            resp = self._call(self._table.scan, **kwargs)
            total += resp.get("Count", 0)
            if "LastEvaluatedKey" not in resp:
                return total
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
