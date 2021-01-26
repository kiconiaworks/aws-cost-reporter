import datetime
import json
import tempfile
from pathlib import Path

from pacioli.charts.create import create_daily_chart_figure, create_daily_pie_chart_figure
from pacioli.functions import add_previous_month_cost_diff, check_phantomjs, format_to_dataframe, generate_daily_chart_image, group_by_cost_cumsum
from PIL import Image

TEST_DATA_DIRECTORY = Path(__file__).absolute().parent / "data"


def test_format_to_dataframe():
    COST_JSON_FILEPATH = TEST_DATA_DIRECTORY / "collect_account_basic_account_metrics__result.json"
    with COST_JSON_FILEPATH.open("r", encoding="utf8") as sample_data_json:
        sample_data = json.loads(sample_data_json.read())
        target_month_start = datetime.datetime(2019, 2, 1)
        df = format_to_dataframe(sample_data)
        df["group2"] = ""  # Accountのみで集計する
        df = group_by_cost_cumsum(df)
        df = add_previous_month_cost_diff(df, target_month_start)

    figure, current_cost, previous_cost = create_daily_chart_figure(df)

    assert figure
    assert current_cost
    assert previous_cost


def test_generate_daily_chart_image():
    check_phantomjs()
    COST_JSON_FILEPATH = TEST_DATA_DIRECTORY / "collect_account_basic_account_metrics__result.json"
    with COST_JSON_FILEPATH.open("r", encoding="utf8") as sample_data_json:
        sample_data = json.loads(sample_data_json.read())

        target_month_start = datetime.datetime(2019, 2, 1)
        df = format_to_dataframe(sample_data)
        df["group2"] = ""  # Accountのみで集計する
        df = group_by_cost_cumsum(df)
        df = add_previous_month_cost_diff(df, target_month_start)

    figure, current_cost, previous_cost = create_daily_chart_figure(df)

    image_buffer = generate_daily_chart_image(figure)
    with tempfile.NamedTemporaryFile() as temp:
        temp.write(image_buffer.read())
        temp.seek(0)
        img = Image.open(temp.name)
        img.verify()
        assert img


def test_generate_pie_chart_image():
    check_phantomjs()
    COST_JSON_FILEPATH = TEST_DATA_DIRECTORY / "collect_account_basic_account_metrics__result.json"
    with COST_JSON_FILEPATH.open("r", encoding="utf8") as sample_data_json:
        sample_data = json.loads(sample_data_json.read())

        target_month_start = datetime.datetime(2019, 2, 1)
        df = format_to_dataframe(sample_data)
        df = group_by_cost_cumsum(df)
        df = add_previous_month_cost_diff(df, target_month_start)

    chart_figures, _ = create_daily_pie_chart_figure(df)

    image_buffer = generate_daily_chart_image(chart_figures)
    with tempfile.NamedTemporaryFile() as temp:
        temp.write(image_buffer.read())
        temp.seek(0)
        img = Image.open(temp.name)
        img.verify()
        assert img
