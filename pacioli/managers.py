"""Key class for interfacing with and obtaining data from the AWS CostExplorer API."""

import datetime
import logging
import pprint
from collections import Counter, defaultdict
from operator import attrgetter
from typing import Any

from .aws import CE_CLIENT
from .definitions import AccountCostChange, ProjectCostChange, ProjectServicesCost, ServiceCost
from .functions import get_accountid_mapping, get_month_starts, get_tag_display_mapping
from .settings import GROUPBY_TAG_NAME, MIN_PERCENTAGE_CHANGE, TAX_SERVICE_NAME

logger = logging.getLogger(__name__)

DEFAULT_EXCLUDE_TAGS = ["Tax"]


def sort_by_periodstart(entry: dict) -> datetime.datetime:
    """Sort CostExplorer results by Period Start"""
    return datetime.datetime.fromisoformat(entry["TimePeriod"]["Start"]).replace(tzinfo=datetime.UTC)


class CostManager:
    """Class intended to manage desired CostExplorer ('ce') operations."""

    def _collect_account_cost(
        self, start: datetime.date, end: datetime.date, group_by: list[dict], granularity: str = "DAILY"
    ) -> dict:
        logger.info(f"start={start}, end={end}, granularity={granularity}, group_by={group_by}")
        if start == end:
            # Validation error occurs if start == end
            # An error occurred (ValidationException) when calling the GetCostAndUsage operation:
            #   - Start date (and hour) should be before end date (and hour)
            logger.warning(f"start({start}) == end({end}), incrementing end")
            end += datetime.timedelta(days=1)
            logger.info(f"end={end}")

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

    def collect_account_service_metrics(
        self, start: datetime.date, end: datetime.date, granularity: str = "DAILY"
    ) -> dict:
        """Collect account/service metrics."""
        group_by = [
            {"Type": "DIMENSION", "Key": "LINKED_ACCOUNT"},
        ]
        return self._collect_account_cost(start, end, group_by, granularity)

    def collect_groupbytag_service_metrics(
        self, start: datetime.date, end: datetime.date, granularity: str = "DAILY", include_services: bool = True
    ) -> dict:
        """Collect tag/service metrics."""
        group_by = [
            {"Type": "TAG", "Key": GROUPBY_TAG_NAME},
        ]
        if include_services:
            # To breakdown "EC2 - Other" USAGE_TYPE may be used
            # -- however, max of 2 dimensions are only supported.
            # -- May want to create a new function to breakdown "EC2 - Other" only costs.
            # {"Type": "DIMENSION", "Key": "USAGE_TYPE"}
            group_by.append({"Type": "DIMENSION", "Key": "SERVICE"})
        return self._collect_account_cost(start, end, group_by, granularity)

    def get_period_total_tax(self, start: datetime.date, end: datetime.date) -> float:
        """Get the total Tax cost for the given period."""
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

    def get_projectid_itemized_totals(self, start: datetime.date, end: datetime.date) -> dict[str, Counter]:
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
        """Get cost totals for all connected accounts."""
        results = self.collect_account_service_metrics(start, end)
        c = Counter()
        for period in results["ResultsByTime"]:
            for group in period["Groups"]:
                accountid = "".join(group["Keys"])
                c[accountid] += float(group["Metrics"]["UnblendedCost"]["Amount"])
        return c

    def get_change_in_accounts(self, now: datetime.date | None = None) -> list[AccountCostChange]:
        if not now:
            now = datetime.datetime.now(datetime.UTC)

        most_recent_full_date, current_month_start, previous_month_start = get_month_starts(now)
        start = previous_month_start
        end = most_recent_full_date

        accountis_name_mapping = get_accountid_mapping()
        results = self.collect_account_service_metrics(start, end)
        daily_cumsum = {}
        earliest = None
        latest = None
        for period in results["ResultsByTime"]:
            day = datetime.datetime.fromisoformat(period["TimePeriod"]["Start"]).replace(tzinfo=datetime.UTC)
            if day.date() > most_recent_full_date:
                continue
            for group in period["Groups"]:
                account_id = "".join(group["Keys"])
                if account_id not in daily_cumsum:
                    daily_cumsum[account_id] = {}
                if day.month not in daily_cumsum[account_id]:
                    daily_cumsum[account_id][day.month] = {}
                previous_total = 0 if day.day == 1 else daily_cumsum[account_id][day.month][day.day - 1]
                daily_cumsum[account_id][day.month][day.day] = previous_total + float(
                    group["Metrics"]["UnblendedCost"]["Amount"]
                )
            if not earliest or day < earliest:
                earliest = day
            if not latest or day > latest:
                latest = day
        if latest.date() > most_recent_full_date:
            latest = most_recent_full_date

        logger.info(f"latest={latest}")
        logger.debug("daily_cumsum:")
        logger.debug(pprint.pformat(daily_cumsum, indent=4))
        account_change_data = []
        for account_id in daily_cumsum:
            current = daily_cumsum[account_id][latest.month][latest.day]
            previous_month_day = latest.day
            if previous_month_day not in daily_cumsum[account_id][earliest.month]:
                previous_month_day -= 1
            previous = daily_cumsum[account_id][earliest.month][previous_month_day]
            percentage_change = 0.0
            if current >= MIN_PERCENTAGE_CHANGE and previous >= MIN_PERCENTAGE_CHANGE:  # only update change if >= 0.01
                percentage_change = round((current / previous - 1.0) * 100, 1)
            account_display_name = accountis_name_mapping.get(account_id, "UNDEFINED")
            change_data = AccountCostChange(
                id=account_id,
                name=account_display_name,
                date=latest.date(),
                current_cost=current,
                previous_cost=previous,
                percentage_change=percentage_change,
            )
            account_change_data.append(change_data)
        return account_change_data

    @staticmethod
    def _get_project_change(
        daily_cumsum: defaultdict[Any, dict], earliest_date: datetime.date, latest_date: datetime.date
    ) -> list[ProjectCostChange]:
        """Get project change from 2 month daily cumulative sum dictionary."""
        all_change_data = []
        id_mapping = get_tag_display_mapping()
        for project_id_raw, project_data in daily_cumsum.items():
            current = None
            previous = None
            percentage_change = None

            # get project current cost (find latest day)
            latest_day = latest_date.day
            while latest_day >= 1 and latest_day not in project_data[latest_date.month]:
                latest_day -= 1

            if latest_day >= 1:
                current = project_data[latest_date.month][latest_day]
                previous_month_day = latest_date.day
                if earliest_date.month in project_data:
                    if previous_month_day not in project_data[earliest_date.month]:
                        previous_month_day -= 1

                    if previous_month_day in project_data[earliest_date.month]:
                        previous = project_data[earliest_date.month][previous_month_day]
                        percentage_change = 0.0
                        # only update change if >= MIN_PERCENTAGE_CHANGE
                        if current >= MIN_PERCENTAGE_CHANGE and previous >= MIN_PERCENTAGE_CHANGE:
                            percentage_change = round((current / previous - 1.0) * 100, 1)
            project_id = project_id_raw.replace("ProjectId$", "").strip()
            project_name = id_mapping.get(project_id, "UNDEFINED")
            project_change_data = ProjectCostChange(
                raw_id=project_id_raw,
                name=project_name,
                date=latest_date,
                current_cost=current,
                previous_cost=previous,
                percentage_change=percentage_change,
            )
            all_change_data.append(project_change_data)
        return all_change_data

    def get_change_in_projects(self, now: datetime.date | None = None) -> list[ProjectCostChange]:
        """Get change in projects for the given period."""
        if not now:
            now = datetime.datetime.now(datetime.UTC)

        most_recent_full_date, current_month_start, previous_month_start = get_month_starts(now)
        start = previous_month_start
        end = most_recent_full_date

        results = self.collect_groupbytag_service_metrics(start, end, include_services=False)
        daily_cumsum = defaultdict(dict)
        earliest = None
        latest = None
        for period in sorted(results["ResultsByTime"], key=sort_by_periodstart):
            day = datetime.datetime.fromisoformat(period["TimePeriod"]["Start"]).replace(tzinfo=datetime.UTC)
            for group in period["Groups"]:
                project_id = "".join(group["Keys"])
                if day.month not in daily_cumsum[project_id]:
                    daily_cumsum[project_id][day.month] = {}
                if day.day == 1 or day.day - 1 not in daily_cumsum[project_id][day.month]:
                    previous_total = 0
                else:
                    previous_total = daily_cumsum[project_id][day.month][day.day - 1]
                daily_cumsum[project_id][day.month][day.day] = previous_total + float(
                    group["Metrics"]["UnblendedCost"]["Amount"]
                )
            if not earliest or day < earliest:
                earliest = day
            if not latest or day > latest:
                latest = day

        if latest.date() > most_recent_full_date:
            latest = most_recent_full_date
        change_data = self._get_project_change(daily_cumsum, earliest, latest)
        return change_data


class ReportManager:
    """Use CostManager to format results for reporting."""

    def __init__(
        self,
        generation_datetime: datetime.datetime | None = None,
        previous_month_start: datetime.date | None = None,
        current_month_start: datetime.date | None = None,
        most_recent_full_date: datetime.date | None = None,
    ) -> None:
        if not generation_datetime:
            generation_datetime = datetime.datetime.now(datetime.UTC)
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
        """Get the current taxed value for the current month"""
        result = self.cm.get_period_total_tax(start=self.current_month_start, end=self.most_recent_full_date)
        return result

    def generate_accounts_report(self) -> list[AccountCostChange]:
        account_change_data = self.cm.get_change_in_accounts(self.generation_datetime)
        return sorted(
            account_change_data, key=attrgetter("current_cost"), reverse=True
        )  # sort biggest -> smallest current cost

    def generate_projectid_report(self) -> list[ProjectCostChange]:
        """Get list of Project Change Data for the report `generation_datetime` sorted by largest cost to smallest"""
        data = self.cm.get_change_in_projects(self.generation_datetime)
        return sorted(data, key=attrgetter("current_cost"), reverse=True)  # sort biggest -> smallest current cost

    def generate_projectid_itemized_report(self) -> list[ProjectServicesCost]:
        """NOTE: Tax is excluded from results"""
        results: dict[str, Counter] = self.cm.get_projectid_itemized_totals(
            start=self.current_month_start, end=self.most_recent_full_date
        )

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
        id_mapping = get_tag_display_mapping()
        all_project_services: list[ProjectServicesCost] = []
        for project_id_raw, services in results.items():
            project_id = project_id_raw.replace("ProjectId$", "").strip()
            name = id_mapping.get(project_id, "UNDEFINED")
            project_services_cost = ProjectServicesCost(
                raw_id=project_id_raw,
                name=name,
                date=self.most_recent_full_date,
                services=[],
            )
            service_costs = []
            for service_name, cost in services.items():
                # exclude Tax
                if service_name == TAX_SERVICE_NAME:
                    logger.info(f"excluding tag '{TAX_SERVICE_NAME}' {cost}")
                    continue
                service_cost = ServiceCost(
                    name=service_name,
                    cost=cost,
                )
                service_costs.append(service_cost)
            # sort project services by cost
            # biggest -> smallest
            services_sorted_by_cost = sorted(service_costs, key=attrgetter("cost"), reverse=True)
            project_services_cost.services = services_sorted_by_cost
            all_project_services.append(project_services_cost)

        return sorted(
            all_project_services, key=attrgetter("total_cost"), reverse=True
        )  # sort biggest -> smallest current cost
