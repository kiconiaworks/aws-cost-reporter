import json
import tempfile
from pathlib import Path

from PIL import Image

from pacioli.functions import format_to_dataframe, generate_daily_chart_image
from pacioli.charts.create import create_daily_chart_figure

TEST_DATA_DIRECTORY = Path(__file__).absolute().parent / 'data'


def test_format_to_dataframe():
    COST_JSON_FILEPATH = TEST_DATA_DIRECTORY / 'collect_account_basic_account_metrics__result.json'
    with COST_JSON_FILEPATH.open('r', encoding='utf8') as sample_data_json:
        sample_data = json.loads(sample_data_json.read())
        df = format_to_dataframe(sample_data)
    figure, current_cost, previous_cost = create_daily_chart_figure(df)
    assert figure


def test_generate_daily_chart_image():
    COST_JSON_FILEPATH = TEST_DATA_DIRECTORY / 'collect_account_basic_account_metrics__result.json'
    with COST_JSON_FILEPATH.open('r', encoding='utf8') as sample_data_json:
        sample_data = json.loads(sample_data_json.read())
        df = format_to_dataframe(sample_data)
    figure, current_cost, previous_cost = create_daily_chart_figure(df)
    image_buffer = generate_daily_chart_image(figure)
    with tempfile.NamedTemporaryFile() as temp:
        temp.write(image_buffer.read())
        temp.seek(0)
        img = Image.open(temp.name)
        img.verify()
        assert img
