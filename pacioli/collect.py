"""
Key class for interfacing with and obtaining data from the AWS CostExplorer API.
"""
import datetime
import logging
from typing import List

import boto3

from .settings import GROUPBY_TAG_NAME

logger = logging.getLogger(__name__)


class CostManager:
    """
    Class intended to manage desired CostExplorer ('ce') operations.
    """

    def __init__(self):
        self.ce_client = boto3.client("ce")

    def _collect_account_cost(self, start: datetime.date, end: datetime.date, group_by: List[dict], granularity: str = "DAILY") -> dict:
        logger.info(f"start={start}, end={end}, granularity={granularity}, group_by={group_by}")

        all_results = {"ResultsByTime": []}

        response = self.ce_client.get_cost_and_usage(
            TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
            Granularity=granularity,
            GroupBy=group_by,
            Metrics=["BlendedCost", "UnblendedCost", "UsageQuantity"],
        )
        all_results["ResultsByTime"].extend(response["ResultsByTime"])

        # handle paged responses
        while "NextPageToken" in response and response["NextPageToken"]:
            response = self.ce_client.get_cost_and_usage(
                TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
                Granularity=granularity,
                GroupBy=group_by,
                Metrics=["BlendedCost", "UnblendedCost", "UsageQuantity"],
                NextPageToken=response["NextPageToken"],
            )
            all_results["ResultsByTime"].extend(response["ResultsByTime"])

        return all_results

    def collect_account_service_metrics(self, start: datetime.date, end: datetime.date, granularity="DAILY") -> dict:
        """
        Collect account/service metrics.
        """
        group_by = [
            {"Type": "DIMENSION", "Key": "LINKED_ACCOUNT"},
            {"Type": "DIMENSION", "Key": "SERVICE"},
        ]
        return self._collect_account_cost(start, end, group_by, granularity)

    def collect_groupbytag_service_metrics(self, start: datetime.date, end: datetime.date, granularity="DAILY") -> dict:
        """
        Collect tag/service metrics.
        """
        group_by = [
            {"Type": "TAG", "Key": GROUPBY_TAG_NAME},
            {"Type": "DIMENSION", "Key": "SERVICE"},
        ]
        return self._collect_account_cost(start, end, group_by, granularity)
