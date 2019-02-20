import json
import datetime
from pathlib import Path

from pacioli.functions import format_to_dataframe, _get_month_starts


TEST_DATA_DIRECTORY = Path(__file__).absolute().parent / 'data'


def test_format_to_dataframe():
    COST_JSON_FILEPATH = TEST_DATA_DIRECTORY / 'collect_account_basic_account_metrics__result.json'
    with COST_JSON_FILEPATH.open('r', encoding='utf8') as sample_data_json:
        sample_data = json.loads(sample_data_json.read())
        df = format_to_dataframe(sample_data)
    assert not df.empty


def test___get_month_starts():
    d = datetime.datetime(2019, 1, 5)
    expected_current_month_start = datetime.date(2019, 1, 1)
    expected_previous_month_start = datetime.date(2018, 12, 1)
    _, actual_current_month_start, actual_previous_month_start = _get_month_starts(d)

    assert actual_current_month_start == expected_current_month_start
    assert actual_previous_month_start == expected_previous_month_start
