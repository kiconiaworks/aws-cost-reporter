import datetime
import json
from io import BytesIO
from pathlib import Path

from pacioli.aws import S3_CLIENT
from pacioli.functions import get_month_starts, get_tag_display_mapping

from .utils import reset_buckets

TEST_DATA_DIRECTORY = Path(__file__).absolute().parent / "data"


def test__get_month_starts():
    d = datetime.datetime(2019, 1, 5)
    expected_current_month_start = datetime.date(2019, 1, 1)
    expected_previous_month_start = datetime.date(2018, 12, 1)
    _, actual_current_month_start, actual_previous_month_start = get_month_starts(d)

    assert actual_current_month_start == expected_current_month_start
    assert actual_previous_month_start == expected_previous_month_start


def test__get_tag_display_mapping__no_definition():
    expected = {}
    actual = get_tag_display_mapping()
    assert actual == expected


def test__get_tag_display_mapping__invalid_key():
    test_bucket = "test-mapping-bucket"
    s3_uri = f"s3://{test_bucket}/invalid-key"
    reset_buckets(buckets=[test_bucket])  # make sure bucket is created!
    expected = {}
    actual = get_tag_display_mapping(mapping_s3_uri=s3_uri)
    assert actual == expected


def test__get_tag_display_mapping__invalid_key_contents():
    test_bucket = "test-mapping-bucket"
    key = "testfile.json"
    s3_uri = f"s3://{test_bucket}/{key}"
    reset_buckets(buckets=[test_bucket])  # make sure bucket is created!

    # put bad file
    # encode to utf8 fileobj
    bytesout = BytesIO("invalid content".encode("utf8"))
    bytesout.seek(0)
    S3_CLIENT.upload_fileobj(bytesout, test_bucket, key)

    expected = {}
    actual = get_tag_display_mapping(mapping_s3_uri=s3_uri)
    assert actual == expected


def test__get_tag_display_mapping__valid_key():
    test_bucket = "test-mapping-bucket"
    key = "testfile.json"
    s3_uri = f"s3://{test_bucket}/{key}"
    reset_buckets(buckets=[test_bucket])  # make sure bucket is created!

    # put bad file
    # encode to utf8 fileobj
    expected = {"123-456": "OneTwoThree"}
    bytesout = BytesIO(json.dumps(expected).encode("utf8"))
    bytesout.seek(0)
    S3_CLIENT.upload_fileobj(bytesout, test_bucket, key)
    actual = get_tag_display_mapping(mapping_s3_uri=s3_uri)
    for expected_key, expected_value in expected.items():
        assert expected_key in actual
        assert actual[expected_key] == expected_value
