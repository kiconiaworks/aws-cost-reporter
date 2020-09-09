"""
CLI for testing manually.
"""
import json
import datetime
from io import BytesIO
from typing import Optional

from .event_handlers import post_daily_chart
from .functions import _get_month_starts, prepare_daily_chart_figure, generate_daily_chart_image
from .collect import CostManager


def run():
    """Call the event_handler.post_daily_chart() function."""
    post_daily_chart(None, None)


def test_collect_account_basic_account_metrics(target_datetime: Optional[datetime.datetime] = None) -> dict:
    """
    Run the CostManager.collect_account_basic_account_metrics() function and retrieve the results.
    """
    end, _, previous_month_start = _get_month_starts(target_datetime)

    manager = CostManager()
    result = manager.collect_account_basic_account_metrics(previous_month_start, end)
    return result


def test_collect_account_group_account_project(target_datetime: Optional[datetime.datetime]) -> dict:
    """
    Run the CostManager.collect_account_basic_account_metrics() function and retrieve the results.
    """
    end, _, previous_month_start = _get_month_starts(target_datetime)

    manager = CostManager()
    result = manager.collect_account_group_account_project(previous_month_start, end)
    return result


def test_graph_image_creation() -> BytesIO:
    """
    Run graph image creation for the current date.
    """
    now = datetime.datetime.now()
    chart_figure = prepare_daily_chart_figure(now)
    image_bytes = generate_daily_chart_image(chart_figure)
    return image_bytes


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--test',
                        action='store_true',
                        default=False,
                        help='If given, results will NOT posted to slack, CostManager.collect_account_basic_account_metrics() output displayed!')

    args = parser.parse_args()
    if args.test:
        cost_manager_collect_result = test_collect_account_basic_account_metrics()
        print(json.dumps(cost_manager_collect_result, indent=4))

        test_chart_filename = 'test-image.png'
        print(f'writing ({test_chart_filename}) ...')
        with open(test_chart_filename, 'wb') as image_out:
            image_bytes = test_graph_image_creation()
            image_out.write(image_bytes.read())
    else:
        run()
