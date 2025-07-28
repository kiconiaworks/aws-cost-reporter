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
from .settings import BREAKDOWN_EC2_OTHER, GROUPBY_TAG_NAME, MIN_PERCENTAGE_CHANGE, TAX_SERVICE_NAME

logger = logging.getLogger(__name__)

DEFAULT_EXCLUDE_TAGS = ["Tax"]

# Constants for magic numbers
MIN_GROUP_KEYS_COUNT = 2

# EC2 - Other usage type mapping
EC2_OTHER_USAGE_TYPE_MAPPING = {
    # Data Transfer
    "DataTransfer-In-Bytes": "EC2 - Data Transfer In",
    "DataTransfer-Out-Bytes": "EC2 - Data Transfer Out",
    "DataTransfer": "EC2 - Data Transfer",
    "DataTransfer-Regional-Bytes": "EC2 - Regional Data Transfer",
    "DataTransfer-InterZone-In": "EC2 - Inter-AZ Data Transfer In",
    "DataTransfer-InterZone-Out": "EC2 - Inter-AZ Data Transfer Out",
    # Elastic IP
    "ElasticIP:IdleAddress": "EC2 - Elastic IP (Idle)",
    "ElasticIP:AdditionalAddress": "EC2 - Elastic IP (Additional)",
    # NAT Gateway
    "NatGateway-Hours": "EC2 - NAT Gateway Hours",
    "NatGateway-Bytes": "EC2 - NAT Gateway Data Processing",
    # VPC Endpoints
    "VpcEndpoint-Hours": "EC2 - VPC Endpoint Hours",
    "VpcEndpoint-Bytes": "EC2 - VPC Endpoint Data Processing",
    # Load Balancer (sometimes appears under EC2 - Other)
    "LoadBalancerUsage": "EC2 - Load Balancer Usage",
    # EBS Optimized
    "EBSOptimized": "EC2 - EBS Optimized",
    # Dedicated Hosts
    "DedicatedUsage": "EC2 - Dedicated Host",
    # Spot Instances
    "SpotUsage": "EC2 - Spot Instance Usage",
    # Instance Store
    "InstanceStore": "EC2 - Instance Store",
    # Default fallback
    "Unknown": "EC2 - Other (Unknown)",
}


def sort_by_periodstart(entry: dict) -> datetime.datetime:
    """Sort CostExplorer results by Period Start"""
    return datetime.datetime.fromisoformat(entry["TimePeriod"]["Start"]).replace(tzinfo=datetime.UTC)


def categorize_ec2_other_usage_type(usage_type: str) -> str:
    """Categorize EC2 - Other usage types into more readable descriptions."""
    # Try to match usage type to known patterns
    for pattern, description in EC2_OTHER_USAGE_TYPE_MAPPING.items():
        if pattern.lower() in usage_type.lower():
            return f"{description} ({usage_type})"
    # If no match, return a generic description with the usage type
    return f"EC2 - Other ({usage_type})"


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

    def get_projectid_itemized_totals(
        self, start: datetime.date, end: datetime.date, breakdown_ec2_other: bool = False
    ) -> dict[str, Counter]:
        """
        :param breakdown_ec2_other: If True, break down "EC2 - Other" costs into specific usage types
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

        # If breakdown_ec2_other is True, process EC2 - Other costs
        if breakdown_ec2_other:
            projects_with_ec2_other = [
                projectid
                for projectid, services in c.items()
                if "EC2 - Other" in services and services["EC2 - Other"] > 0
            ]

            if projects_with_ec2_other:
                logger.info(f"Breaking down EC2 - Other costs for {len(projects_with_ec2_other)} projects")
                ec2_other_breakdown = self._get_ec2_other_breakdown_for_projects(projects_with_ec2_other, start, end)

                # Replace EC2 - Other with breakdown for each project
                for projectid in projects_with_ec2_other:
                    if projectid in ec2_other_breakdown and ec2_other_breakdown[projectid]:
                        # Remove the generic "EC2 - Other" entry
                        del c[projectid]["EC2 - Other"]
                        # Add the breakdown entries
                        for usage_type, cost in ec2_other_breakdown[projectid].items():
                            c[projectid][usage_type] += cost

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

    def _get_previous_value(self, account_id: str, month: int, previous_month_day: int, daily_cumsum: dict) -> int:
        if previous_month_day <= 1:
            logger.debug(
                f"previous_month_day {previous_month_day} is <= 1, setting previous to 0 for account {account_id}"
            )
            previous = 0
        elif previous_month_day not in daily_cumsum[account_id][month]:
            logger.debug(
                f"previous_month_day {previous_month_day} not found in daily_cumsum for account {account_id}, "
                f"setting previous to 0"
            )
            previous = 0
        elif previous_month_day in daily_cumsum[account_id][month]:
            # get previous total for the day
            previous = daily_cumsum[account_id][month][previous_month_day]
            logger.debug(
                f"previous_month_day {previous_month_day} found in daily_cumsum for account {account_id}, "
                f"setting previous to {previous}"
            )
        else:
            logger.warning(
                f"previous_month_day {previous_month_day} not found in daily_cumsum for account {account_id}"
            )
            previous = 0
        return previous

    def get_change_in_accounts(self, now: datetime.date | None = None) -> list[AccountCostChange]:
        if not now:
            now = datetime.datetime.now(datetime.UTC)

        most_recent_full_date, current_month_start, previous_month_start = get_month_starts(now)
        start = previous_month_start
        end = most_recent_full_date

        accountis_name_mapping = get_accountid_mapping()
        results = self.collect_account_service_metrics(start, end)
        daily_cumsum = defaultdict(lambda: defaultdict(dict))
        earliest = None
        latest = None
        for period in results["ResultsByTime"]:
            day = datetime.datetime.fromisoformat(period["TimePeriod"]["Start"]).replace(tzinfo=datetime.UTC)
            if day.date() > most_recent_full_date:
                continue
            for group in period["Groups"]:
                account_id = "".join(group["Keys"])
                previous_day = day.day - 1
                if any((day.day == 1, previous_day not in daily_cumsum[account_id][day.month])):
                    previous_total = 0
                else:
                    # get previous total for the day
                    previous_total = daily_cumsum[account_id][day.month][previous_day]
                daily_cumsum[account_id][day.month][day.day] = previous_total + float(
                    group["Metrics"]["UnblendedCost"]["Amount"]
                )
            if not earliest or day < earliest:
                earliest = day
            if not latest or day > latest:
                latest = day
        if latest.date() > most_recent_full_date:
            latest = most_recent_full_date

        account_change_data = []
        for account_id in daily_cumsum:
            current = daily_cumsum[account_id][latest.month][latest.day]
            previous_month_day = latest.day
            if previous_month_day not in daily_cumsum[account_id][earliest.month]:
                previous_month_day -= 1
            previous = self._get_previous_value(
                account_id, month=earliest.month, previous_month_day=previous_month_day, daily_cumsum=daily_cumsum
            )

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

            # get project current cost (find latest day)
            latest_day = latest_date.day
            project_id = project_id_raw.replace("ProjectId$", "").strip()
            project_name = id_mapping.get(project_id, "UNDEFINED")
            if latest_date.month in project_data:
                previous = 0.0
                percentage_change = 0.0
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
            else:
                # Project does not incur any cost in the latest month
                logger.warning(f"project_id {project_id_raw} not found in daily_cumsum for month {latest_date.month}")
                logger.warning("project_data:")
                logger.warning(pprint.pformat(project_data, indent=4))
                current = 0.0
                previous = 0.0
                percentage_change = 0.0
                if earliest_date.month in project_data:
                    previous_month_day = latest_date.day
                    if previous_month_day not in project_data[earliest_date.month]:
                        previous_month_day -= 1

                    if previous_month_day in project_data[earliest_date.month]:
                        previous = project_data[earliest_date.month][previous_month_day]

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

    def _get_ec2_other_breakdown_for_projects(
        self, project_ids: list[str], start: datetime.date, end: datetime.date
    ) -> dict[str, dict[str, float]]:
        """Get detailed breakdown of EC2 - Other costs for specific projects using USAGE_TYPE dimension."""
        # Build filter for the specific projects and EC2 - Other service
        project_filters = []
        for project_id in project_ids:
            # Remove the prefix if present
            clean_project_id = project_id.replace(f"{GROUPBY_TAG_NAME}$", "")
            project_filters.append(
                {
                    "And": [
                        {"Tags": {"Key": GROUPBY_TAG_NAME, "Values": [clean_project_id]}},
                        {"Dimensions": {"Key": "SERVICE", "Values": ["EC2 - Other"]}},
                    ]
                }
            )

        # If multiple projects, combine with OR
        filters = {"Or": project_filters} if len(project_filters) > 1 else project_filters[0]

        # Use SERVICE and USAGE_TYPE to break down EC2 - Other
        group_by = [{"Type": "TAG", "Key": GROUPBY_TAG_NAME}, {"Type": "DIMENSION", "Key": "USAGE_TYPE"}]

        try:
            # Get cost data from AWS
            all_results = {"ResultsByTime": []}
            response = CE_CLIENT.get_cost_and_usage(
                TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
                Granularity="DAILY",
                GroupBy=group_by,
                Metrics=["UnblendedCost"],
                Filter=filters,
            )
            all_results["ResultsByTime"].extend(response["ResultsByTime"])

            # Handle paged responses
            while "NextPageToken" in response and response["NextPageToken"]:
                response = CE_CLIENT.get_cost_and_usage(
                    TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
                    Granularity="DAILY",
                    GroupBy=group_by,
                    Metrics=["UnblendedCost"],
                    Filter=filters,
                    NextPageToken=response["NextPageToken"],
                )
                all_results["ResultsByTime"].extend(response["ResultsByTime"])

            # Process results into project -> usage type -> cost mapping
            breakdown = defaultdict(lambda: defaultdict(float))
            for period in all_results["ResultsByTime"]:
                for group in period["Groups"]:
                    if len(group["Keys"]) >= MIN_GROUP_KEYS_COUNT:
                        project_id_raw, usage_type = group["Keys"]
                        amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                        if amount > 0:
                            # Create a more descriptive name
                            detailed_name = categorize_ec2_other_usage_type(usage_type)
                            breakdown[project_id_raw][detailed_name] += amount

            return dict(breakdown)

        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Failed to break down EC2 - Other costs: {e}")
            return {}


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
            start=self.current_month_start, end=self.most_recent_full_date, breakdown_ec2_other=BREAKDOWN_EC2_OTHER
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
