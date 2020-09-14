import json
import datetime
from io import BytesIO
from pathlib import Path

from pacioli import settings
from pacioli.aws import S3_CLIENT
from pacioli.functions import format_to_dataframe, group_by_cost_cumsum, add_previous_month_cost_diff, _get_month_starts, _get_tag_display_mapping

from .utils import reset_buckets


TEST_DATA_DIRECTORY = Path(__file__).absolute().parent / 'data'


def test_format_to_dataframe():
    COST_JSON_FILEPATH = TEST_DATA_DIRECTORY / 'collect_account_basic_account_metrics__result.json'
    with COST_JSON_FILEPATH.open('r', encoding='utf8') as sample_data_json:
        sample_data = json.loads(sample_data_json.read())
        target_month_start = datetime.datetime(2019, 2, 1)
        df = format_to_dataframe(sample_data)
        df["group2"] = ""  # Accountのみで集計する
        df = group_by_cost_cumsum(df)
        df = add_previous_month_cost_diff(df, target_month_start)
    assert not df.empty
    assert all(header in df.columns.values for header in ('000000000001', '000000000002', 'previous_month_total'))

    # provides the cumulative sum for each day (including the previous)
    expected_000000000001_cumsum = 8504.0
    expected_000000000002_cumsum = 9878.0

    actual_000000000001_sum = df['000000000001'].sum()
    actual_000000000002_sum = df['000000000002'].sum()

    assert actual_000000000001_sum == expected_000000000001_cumsum
    assert actual_000000000002_sum == expected_000000000002_cumsum


def test__get_month_starts():
    d = datetime.datetime(2019, 1, 5)
    expected_current_month_start = datetime.date(2019, 1, 1)
    expected_previous_month_start = datetime.date(2018, 12, 1)
    _, actual_current_month_start, actual_previous_month_start = _get_month_starts(d)

    assert actual_current_month_start == expected_current_month_start
    assert actual_previous_month_start == expected_previous_month_start


def test__get_tag_display_mapping__no_definition():
    expected = {}
    actual = _get_tag_display_mapping()
    assert actual == expected


def test__get_tag_display_mapping__invalid_key():
    test_bucket = "test-mapping-bucket"
    s3_uri = f"s3://{test_bucket}/invalid-key"
    reset_buckets(buckets=[test_bucket])  # make sure bucket is created!
    expected = {}
    actual = _get_tag_display_mapping(mapping_s3_uri=s3_uri)
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
    actual = _get_tag_display_mapping(mapping_s3_uri=s3_uri)
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
    actual = _get_tag_display_mapping(mapping_s3_uri=s3_uri)
    for expected_key, expected_value in expected.items():
        assert expected_key in actual
        assert actual[expected_key] == expected_value
