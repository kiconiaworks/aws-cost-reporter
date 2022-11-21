"""
Key class for interfacing with and obtaining data from the AWS CostExplorer API.
"""
import datetime
import logging
from collections import Counter, defaultdict
from typing import List, Optional

from .aws import CE_CLIENT
from .functions import get_month_starts
from .settings import GROUPBY_TAG_NAME

logger = logging.getLogger(__name__)

DEFAULT_EXCLUDE_TAGS = ["Tax"]


class CostManager:
    """
    Class intended to manage desired CostExplorer ('ce') operations.
    """

    def _collect_account_cost(self, start: datetime.date, end: datetime.date, group_by: List[dict], granularity: str = "DAILY") -> dict:
        logger.info(f"start={start}, end={end}, granularity={granularity}, group_by={group_by}")

        all_results = {"ResultsByTime": []}

        response = CE_CLIENT.get_cost_and_usage(
            TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
            Granularity=granularity,
            GroupBy=group_by,
            Metrics=["BlendedCost", "UnblendedCost", "UsageQuantity"],
        )
        all_results["ResultsByTime"].extend(response["ResultsByTime"])

        # handle paged responses
        while "NextPageToken" in response and response["NextPageToken"]:
            response = CE_CLIENT.get_cost_and_usage(
                TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
                Granularity=granularity,
                GroupBy=group_by,
                Metrics=["UnblendedCost", "UsageQuantity"],
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
        ]
        return self._collect_account_cost(start, end, group_by, granularity)

    def collect_groupbytag_service_metrics(
        self, start: datetime.date, end: datetime.date, granularity="DAILY", include_services: bool = True
    ) -> dict:
        """
        Collect tag/service metrics.
        """
        group_by = [
            {"Type": "TAG", "Key": GROUPBY_TAG_NAME},
        ]
        if include_services:
            group_by.append({"Type": "DIMENSION", "Key": "SERVICE"})
        return self._collect_account_cost(start, end, group_by, granularity)

    def get_period_total_tax(self, start: datetime.date, end: datetime.date) -> float:
        group_by = [{"Type": "DIMENSION", "Key": "RECORD_TYPE"}]
        daily_results = self._collect_account_cost(start, end, group_by, granularity="DAILY")
        c = Counter()
        for period in daily_results["ResultsByTime"]:
            for group in period["Groups"]:
                key = "".join(group["Keys"])
                if key == "Tax":
                    amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                    c[key] += amount
        return c["Tax"]

    def get_projectid_totals(self, start: datetime.date, end: datetime.date) -> Counter:
        """
        Sample Data:

            {
                "GroupDefinitions": [
                    {
                        "Type": "TAG",
                        "Key": "ProjectId"
                    }
                ],
                "ResultsByTime": [
                    {
                        "TimePeriod": {
                            "Start": "2022-11-07",
                            "End": "2022-11-08"
                        },
                        "Total": {},
                        "Groups": [
                            {
                                "Keys": [
                                    "ProjectId$"
                                ],
                                "Metrics": {
                                    "BlendedCost": {
                                        "Amount": "11.4910253801",
                                        "Unit": "USD"
                                    },
                                    "UsageQuantity": {
                                        "Amount": "648.6737713369",
                                        "Unit": "N/A"
                                    },
                                    "UnblendedCost": {
                                        "Amount": "11.4896477891",
                                        "Unit": "USD"
                                    }
                                }
                            },
                            {
                                "Keys": [
                                    "ProjectId$2895b79a-c8ff-428c-b45a-e581dad87b84"
                                ],
                                "Metrics": {
                                    "BlendedCost": {
                                        "Amount": "0.0000422887",
                                        "Unit": "USD"
                                    },
                                    "UsageQuantity": {
                                        "Amount": "373.2826915473",
                                        "Unit": "N/A"
                                    },
                                    "UnblendedCost": {
                                        "Amount": "0.0000422887",
                                        "Unit": "USD"
                                    }
                                }
                            },
                        ]
                    }

        """
        daily_results = self.collect_groupbytag_service_metrics(start, end, include_services=False)
        c = Counter()
        for period in daily_results["ResultsByTime"]:
            for group in period["Groups"]:
                key = "".join(group["Keys"])
                amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                c[key] += amount
        return c

    def get_projectid_itemized_totals(self, start: datetime.date, end: datetime.date) -> dict:
        daily_results = self.collect_groupbytag_service_metrics(start, end, include_services=True)
        c = defaultdict(Counter)
        for period in daily_results["ResultsByTime"]:
            for group in period["Groups"]:
                projectid, service = group["Keys"]
                amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                c[projectid][service] += amount
        return c

    def get_account_totals(self, start: datetime.date, end: datetime.date) -> dict:
        results = self.collect_account_service_metrics(start, end)
        c = Counter()
        for period in results["ResultsByTime"]:
            for group in period["Groups"]:
                accountid = "".join(group["Keys"])
                c[accountid] += float(group["Metrics"]["UnblendedCost"]["Amount"])
        return c

    def get_change_in_accounts(self, now: Optional[datetime.date] = None) -> dict:
        """
        :return:
            {
                ACCOUNT_ID: (
                    CURRENT_COST,
                    PREVIOUS_COST,
                    PERCENTAGE_CHANGE,
                ),
                ...
            }
        """
        if not now:
            now = datetime.datetime.now(datetime.timezone.utc)

        most_recent_full_date, current_month_start, previous_month_start = get_month_starts(now)
        start = previous_month_start
        end = most_recent_full_date

        results = self.collect_account_service_metrics(start, end)
        daily_cumsum = {}
        earliest = None
        latest = None
        for period in results["ResultsByTime"]:
            day = datetime.datetime.fromisoformat(period["TimePeriod"]["Start"]).replace(tzinfo=datetime.timezone.utc)

            for group in period["Groups"]:
                account_id = "".join(group["Keys"])
                if account_id not in daily_cumsum:
                    daily_cumsum[account_id] = {}
                if day.month not in daily_cumsum[account_id]:
                    daily_cumsum[account_id][day.month] = {}
                if day.day == 1:
                    previous_total = 0
                else:
                    previous_total = daily_cumsum[account_id][day.month][day.day - 1]
                daily_cumsum[account_id][day.month][day.day] = previous_total + float(group["Metrics"]["UnblendedCost"]["Amount"])
            if not earliest:
                earliest = day
            elif day < earliest:
                earliest = day
            if not latest:
                latest = day
            elif day > latest:
                latest = day
        if latest.date() > most_recent_full_date:
            latest = most_recent_full_date
        change = {}
        for account_id in daily_cumsum.keys():
            current = daily_cumsum[account_id][latest.month][latest.day]
            previous_month_day = latest.day
            if previous_month_day not in daily_cumsum[account_id][earliest.month]:
                previous_month_day -= 1
            previous = daily_cumsum[account_id][earliest.month][previous_month_day]
            percentage_change = round((current / previous - 1.0) * 100, 1)
            change[account_id] = (current, previous, percentage_change)
        return change

    def get_change_in_projects(self, now: Optional[datetime.date] = None):
        if not now:
            now = datetime.datetime.now(datetime.timezone.utc)

        most_recent_full_date, current_month_start, previous_month_start = get_month_starts(now)
        start = previous_month_start
        end = most_recent_full_date

        results = self.collect_groupbytag_service_metrics(start, end, include_services=False)
        daily_cumsum = {}
        earliest = None
        latest = None
        for period in results["ResultsByTime"]:
            day = datetime.datetime.fromisoformat(period["TimePeriod"]["Start"]).replace(tzinfo=datetime.timezone.utc)

            for group in period["Groups"]:
                project_id = "".join(group["Keys"])
                if project_id not in daily_cumsum:
                    daily_cumsum[project_id] = {}
                if day.month not in daily_cumsum[project_id]:
                    daily_cumsum[project_id][day.month] = {}
                if day.day == 1:
                    previous_total = 0
                else:
                    previous_total = daily_cumsum[project_id][day.month][day.day - 1]
                daily_cumsum[project_id][day.month][day.day] = previous_total + float(group["Metrics"]["UnblendedCost"]["Amount"])
            if not earliest:
                earliest = day
            elif day < earliest:
                earliest = day
            if not latest:
                latest = day
            elif day > latest:
                latest = day

        if latest.date() > most_recent_full_date:
            latest = most_recent_full_date
        change = {}
        for project_id in daily_cumsum.keys():
            current = daily_cumsum[project_id][latest.month][latest.day]
            previous_month_day = latest.day
            if previous_month_day not in daily_cumsum[project_id][earliest.month]:
                previous_month_day -= 1
            previous = daily_cumsum[project_id][earliest.month][previous_month_day]
            percentage_change = round((current / previous - 1.0) * 100, 1)
            change[project_id] = (current, previous, percentage_change)
        return change


class ReportManager:
    def __init__(
        self,
        generation_datetime: Optional[datetime.datetime] = None,
        previous_month_start: Optional[datetime.date] = None,
        current_month_start: Optional[datetime.date] = None,
        most_recent_full_date: Optional[datetime.date] = None,
    ):

        if not generation_datetime:
            generation_datetime = datetime.datetime.now(datetime.timezone.utc)
        if not previous_month_start and not current_month_start and not most_recent_full_date:
            logger.info("dates not given, calculating...")
            most_recent_full_date, current_month_start, previous_month_start = get_month_starts(generation_datetime)

        logger.info(f"generation_datetime={generation_datetime}")
        logger.info(f"most_recent_full_date={most_recent_full_date}")
        logger.info(f"current_month_start={current_month_start}")
        logger.info(f"previous_month_start={previous_month_start}")

        self.generation_datetime = generation_datetime
        self.most_recent_full_date = most_recent_full_date
        self.current_month_start = current_month_start
        self.previous_month_start = previous_month_start

        self.cm = CostManager()

    def generate_accounts_report(self) -> list[dict]:
        """
        :return:
            [
                {
                    "id": {ACCOUNT_ID},
                    "name": {ACCOUNT_NAME},
                    "current_cost": {CURRENT_COST},
                    "previous_cost": {PREVIOUS_COST},
                    "percentage_change": {PercentageChange},
                    "
                },
                ...
            ]
        """

        raise NotImplementedError

    def generate_tag_report(self, tag: str = GROUPBY_TAG_NAME, exclude_tags: list[str] = DEFAULT_EXCLUDE_TAGS) -> list[dict]:
        """
        :return:
            [
                {
                    "id": {ACCOUNT_ID},
                    "name": {ACCOUNT_NAME},
                    "current_cost": {CURRENT_COST},
                    "previous_cost": {PREVIOUS_COST},
                    "percentage_change": {PercentageChange},
                    "
                },
                ...
            ]
        """
        raise NotImplementedError

    def generate_tag_itemized_report(self, tag: str = GROUPBY_TAG_NAME, exclude_tags: list[str] = DEFAULT_EXCLUDE_TAGS) -> list[dict]:
        """
        :return:
            [
                {
                    "id": {ACCOUNT_ID},
                    "name": {ACCOUNT_NAME},
                    "current_cost": {CURRENT_COST},
                    "previous_cost": {PREVIOUS_COST},
                    "percentage_change": {PercentageChange},
                    "
                },
                ...
            ]
        """
        raise NotImplementedError
