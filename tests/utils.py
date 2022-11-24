import json
from pathlib import Path
from typing import List

from pacioli import settings
from pacioli.aws import S3_RESOURCE, parse_s3_uri

DATA_DIRECTORY = Path(__file__).parent / "data"


def reset_buckets(buckets: List[str]) -> List[str]:
    """
    Ensure a empty bucket.

    Create a newly s3 bucket if it does not exists and remove all items.
    """
    assert settings.AWS_SERVICE_ENDPOINTS["s3"].startswith(
        ("http://localhost", "http://127.0.0.1")
    ), f'ERROR -- Not running locally, AWS_SERVICE_ENDPOINTS["s3"]={settings.AWS_SERVICE_ENDPOINTS["s3"]}'
    created_buckets = []
    for bucket_name in buckets:
        S3_RESOURCE.create_bucket(Bucket=bucket_name)
        S3_RESOURCE.Bucket(bucket_name).objects.all().delete()
        created_buckets.append(bucket_name)

    return created_buckets


def mock_collect_groupbytag_projectid(*args, **kwargs):
    filepath = DATA_DIRECTORY / "costusage_daily_groupby_projectid.json"
    data = json.loads(filepath.read_text(encoding="utf8"))
    return data


def mock_collect_groupbytag_projectid_services(*args, **kwargs):
    filepath = DATA_DIRECTORY / "costusage_daily_groupby_projectid_with_services.json"
    data = json.loads(filepath.read_text(encoding="utf8"))
    return data


def mock_collect_groupbytag_projectid_services__single_day(*args, **kwargs):
    filepath = DATA_DIRECTORY / "costusage_daily_groupby_projectid_with_services__single_day.json"
    data = json.loads(filepath.read_text(encoding="utf8"))
    return data


def mock_collect_groupby_resoucetype(*args, **kwargs):
    filepath = DATA_DIRECTORY / "costusage_daily_groupby_recordtype.json"
    data = json.loads(filepath.read_text(encoding="utf8"))
    return data


def mock_collect_groupby_linkedaccount(*args, **kwargs):
    filepath = DATA_DIRECTORY / "costusage_daily_groupby_linkedaccount.json"
    data = json.loads(filepath.read_text(encoding="utf8"))
    return data
