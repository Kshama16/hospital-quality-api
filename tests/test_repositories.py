"""The same contract tests run against the SQL and NoSQL implementations."""

import boto3
import pytest
from moto import mock_aws

from app.repositories import DynamoDBHospitalRepository, SQLiteHospitalRepository
from app.repositories.dynamodb import table_definition


@pytest.fixture(params=["sqlite", "dynamodb"])
def repo(request):
    if request.param == "sqlite":
        yield SQLiteHospitalRepository()
    else:
        with mock_aws():
            ddb = boto3.resource("dynamodb", region_name="us-east-1")
            ddb.create_table(**table_definition("hospitals-test"))
            yield DynamoDBHospitalRepository("hospitals-test", resource=ddb)


def test_put_get_round_trip_keeps_types_and_nulls(repo, sample):
    assert repo.put_many(sample) == 5
    h = repo.get("220071")
    assert h == sample[0]
    assert h.overall_rating == 5 and isinstance(h.overall_rating, int)
    assert h.patient_experience_stars is None
    assert repo.get("000000") is None


def test_list_by_state_sorted_and_scan_count(repo, sample):
    repo.put_many(sample)
    assert [h.provider_id for h in repo.list_by_state("MA")] == ["220031", "220046", "220071", "220110"]
    assert repo.list_by_state("TX") == []
    assert repo.count() == 5 and len(list(repo.scan())) == 5


def test_put_is_idempotent(repo, sample):
    repo.put_many(sample)
    repo.put_many(sample[:2])
    assert repo.count() == 5


def test_dynamodb_paginates_large_state():
    """More items than one 1 MB DynamoDB page, so LastEvaluatedKey must be followed."""
    from tests.conftest import make

    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(**table_definition("big"))
        repo = DynamoDBHospitalRepository("big", resource=ddb)
        repo.put_many(make(f"{i:06d}", "X" * 3000, ownership="Y" * 1000) for i in range(400))
        assert len(repo.list_by_state("MA")) == 400 and repo.count() == 400
