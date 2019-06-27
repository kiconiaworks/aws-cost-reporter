import json
import datetime
from pathlib import Path

from pacioli.functions import format_to_dataframe, _get_month_starts


TEST_DATA_DIRECTORY = Path(__file__).absolute().parent / 'data'


def test_format_to_dataframe():
    COST_JSON_FILEPATH = TEST_DATA_DIRECTORY / 'collect_account_basic_account_metrics__result.json'
    with COST_JSON_FILEPATH.open('r', encoding='utf8') as sample_data_json:
        sample_data = json.loads(sample_data_json.read())
        target_month_start = datetime.datetime(2019, 2, 1)
        df = format_to_dataframe(sample_data, target_month_start)
    assert not df.empty
    assert all(header in df.columns.values for header in ('000000000001', '000000000002', 'previous_month_total'))

    expected_000000000001_cumsum = 8504.0
    expected_000000000002_cumsum = 9878.0

    actual_000000000001_sum = df['000000000001'].sum()
    actual_000000000002_sum = df['000000000002'].sum()

    assert actual_000000000001_sum == expected_000000000001_cumsum
    assert actual_000000000002_sum == expected_000000000002_cumsum


def test___get_month_starts():
    d = datetime.datetime(2019, 1, 5)
    expected_current_month_start = datetime.date(2019, 1, 1)
    expected_previous_month_start = datetime.date(2018, 12, 1)
    _, actual_current_month_start, actual_previous_month_start = _get_month_starts(d)

    assert actual_current_month_start == expected_current_month_start
    assert actual_previous_month_start == expected_previous_month_start
