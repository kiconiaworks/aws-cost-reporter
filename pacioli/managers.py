"""
Key class for interfacing with and obtaining data from the AWS CostExplorer API.
"""
import datetime
import logging
from collections import Counter, defaultdict
from operator import itemgetter
from typing import List, Optional

from .aws import CE_CLIENT
from .functions import get_accountid_mapping, get_month_starts, get_tag_display_mapping
from .settings import GROUPBY_TAG_NAME

logger = logging.getLogger(__name__)

DEFAULT_EXCLUDE_TAGS = ["Tax"]


def sort_by_periodstart(entry) -> datetime.datetime:
    """Sort CostExplorer results by Period Start"""
    return datetime.datetime.fromisoformat(entry["TimePeriod"]["Start"]).replace(tzinfo=datetime.timezone.utc)


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
            Metrics=["UnblendedCost", "UsageQuantity"],
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
        """
        Get the total Tax cost for the given period.
        """
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
        """
        :return:
            {
                "{PROJECT_ID}": {
                    "{SERVICE}": {COST},
                    ...
                },
                ...
            }
        """
        daily_results = self.collect_groupbytag_service_metrics(start, end, include_services=True)
        c = defaultdict(Counter)
        for period in daily_results["ResultsByTime"]:
            for group in period["Groups"]:
                projectid, service = group["Keys"]
                amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                c[projectid][service] += amount
        return c

    def get_account_totals(self, start: datetime.date, end: datetime.date) -> dict:
        """
        Get cost totals for all connected accounts.
        """
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
            if day.date() > most_recent_full_date:
                continue
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

    def get_change_in_projects(self, now: Optional[datetime.date] = None) -> dict:
        """
        :return:
            {
                "PROJECT_ID": (current, previous, percentage_change),
                ...
            }
        """
        if not now:
            now = datetime.datetime.now(datetime.timezone.utc)

        most_recent_full_date, current_month_start, previous_month_start = get_month_starts(now)
        start = previous_month_start
        end = most_recent_full_date

        results = self.collect_groupbytag_service_metrics(start, end, include_services=False)
        daily_cumsum = {}
        earliest = None
        latest = None
        for period in sorted(results["ResultsByTime"], key=sort_by_periodstart):
            day = datetime.datetime.fromisoformat(period["TimePeriod"]["Start"]).replace(tzinfo=datetime.timezone.utc)
            for group in period["Groups"]:
                project_id = "".join(group["Keys"])
                if project_id not in daily_cumsum:
                    daily_cumsum[project_id] = {}
                if day.month not in daily_cumsum[project_id]:
                    daily_cumsum[project_id][day.month] = {}
                if day.day == 1 or day.day - 1 not in daily_cumsum[project_id][day.month]:
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
            previous = None
            percentage_change = None
            if earliest.month in daily_cumsum[project_id]:
                if previous_month_day not in daily_cumsum[project_id][earliest.month]:
                    previous_month_day -= 1

                if previous_month_day in daily_cumsum[project_id][earliest.month]:
                    previous = daily_cumsum[project_id][earliest.month][previous_month_day]
                    percentage_change = round((current / previous - 1.0) * 100, 1)
            change[project_id] = (current, previous, percentage_change)
        return change


class ReportManager:
    """
    Use CostManager to format results for reporting.
    """

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

    def get_period_total_tax(self) -> float:
        result = self.cm.get_period_total_tax(start=self.current_month_start, end=self.most_recent_full_date)
        return result

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
        results = self.cm.get_change_in_accounts(self.generation_datetime)
        # reformat to expected output
        data = []
        id_mapping = get_accountid_mapping()
        for account_id, (current, previous, perc_change) in results.items():
            # get account name
            name = id_mapping.get(account_id, "UNDEFINED")
            info = {"id": account_id, "name": name, "current_cost": current, "previous_cost": previous, "percentage_change": perc_change}
            data.append(info)
        return sorted(data, key=itemgetter("current_cost"), reverse=True)  # sort biggest -> smallest current cost

    def generate_projectid_report(self) -> list[dict]:
        """
        :return:
            [
                {
                    "id": {ACCOUNT_ID},
                    "name": {ACCOUNT_NAME},
                    "current_cost": {CURRENT_COST},
                    "previous_cost": {PREVIOUS_COST},
                    "percentage_change": {PercentageChange},
                    "services": [
                        {
                            "name": NAME,
                            "cost": COST,
                        },
                        ...
                    ]
                },
                ...
            ]
        """
        results = self.cm.get_change_in_projects(self.generation_datetime)

        # reformat to expected output
        data = []
        id_mapping = get_tag_display_mapping()
        for project_id_raw, (current, previous, perc_change) in results.items():
            project_id = project_id_raw.replace("ProjectId$", "").strip()
            name = id_mapping.get(project_id, "UNDEFINED")
            info = {"id": project_id, "name": name, "current_cost": current, "previous_cost": previous, "percentage_change": perc_change}
            data.append(info)
        return sorted(data, key=itemgetter("current_cost"), reverse=True)  # sort biggest -> smallest current cost

    def generate_projectid_itemized_report(self) -> list[dict]:
        """
        NOTE: Tax is excluded from results
        :return:
            [
                {
                    "id": {ACCOUNT_ID},
                    "name": {ACCOUNT_NAME},
                    "current_cost": {CURRENT_COST},
                    "previous_cost": None,
                    "services": [
                        ({SERVICE_NAME}, {COST}),
                        ...
                    ]
                },
                ...
            ]
        """
        results = self.cm.get_projectid_itemized_totals(start=self.current_month_start, end=self.most_recent_full_date)

        # results structure:
        # {
        #     "{PROJECT_ID}": {
        #         "{SERVICE}": {COST},
        #         ...
        #     },
        #     ...
        # }
        # reformat to expected output
        # aggregate project services
        all_project_services = defaultdict(Counter)
        tax_service_name = "Tax"
        for project_id_raw, services in results.items():
            for service_name, cost in services.items():
                # remove Tax
                if service_name == tax_service_name:
                    logger.info(f"excluding tag '{tax_service_name}' {cost}")
                    continue
                all_project_services[project_id_raw][service_name] += cost
                all_project_services[project_id_raw]["current_cost"] += cost

        data = []
        id_mapping = get_tag_display_mapping()
        for project_id_raw, services in results.items():
            project_id = project_id_raw.replace("ProjectId$", "").strip()
            name = id_mapping.get(project_id, "UNDEFINED")
            info = {"id": project_id, "name": name, "current_cost": 0, "previous_cost": None, "services": []}
            current_cost = all_project_services[project_id_raw].pop("current_cost", 0)
            project_services = list(all_project_services[project_id_raw].items())

            # sort biggest -> smallest
            info["services"] = sorted(project_services, key=lambda x: x[1], reverse=True)
            info["current_cost"] = current_cost
            data.append(info)

        return sorted(data, key=itemgetter("current_cost"), reverse=True)  # sort biggest -> smallest current cost
