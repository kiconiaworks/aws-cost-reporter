"""
CLI for testing manually
"""
import json

from .event_handlers import post_daily_chart
from .functions import _get_month_starts
from .collect import CostManager


def run():
    """Call the event_handler.post_daily_chart() function"""
    post_daily_chart(None, None)


def test_collect_account_basic_account_metrics() -> dict:
    """
    Run the CostManager.collect_account_basic_account_metrics() function and retrieve the results
    """
    end, previous_month_start, _ = _get_month_starts()
    manager = CostManager()
    result = manager.collect_account_basic_account_metrics(previous_month_start, end)
    return result


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
    else:
        run()
