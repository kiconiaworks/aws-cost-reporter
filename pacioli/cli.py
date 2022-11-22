"""
CLI for testing manually.
"""
import datetime
import json
from typing import Optional

from .functions import get_month_starts
from .handlers.events import post_status
from .managers import CostManager


def run():
    """Call the event_handler.post_daily_chart() function."""
    post_status(None, None)


def test_collect_account_basic_account_metrics(target_datetime: Optional[datetime.datetime] = None) -> dict:
    """
    Run the CostManager.collect_account_basic_account_metrics() function and retrieve the results.
    """
    end, _, previous_month_start = get_month_starts(target_datetime)

    manager = CostManager()
    result = manager.collect_account_basic_account_metrics(previous_month_start, end)
    return result


def test_collect_account_group_account_project(target_datetime: Optional[datetime.datetime]) -> dict:
    """
    Run the CostManager.collect_account_basic_account_metrics() function and retrieve the results.
    """
    end, _, previous_month_start = get_month_starts(target_datetime)

    manager = CostManager()
    result = manager.collect_account_group_account_project(previous_month_start, end)
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--test",
        action="store_true",
        default=False,
        help="If given, results will NOT posted to slack, CostManager.collect_account_basic_account_metrics() output displayed!",
    )

    args = parser.parse_args()
    if args.test:
        cost_manager_collect_result = test_collect_account_basic_account_metrics()
        print(json.dumps(cost_manager_collect_result, indent=4))
    else:
        run()
