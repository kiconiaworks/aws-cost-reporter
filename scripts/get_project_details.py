#!/usr/bin/env python3
"""CLI script to get project details with resources grouped by category."""
# ruff: noqa: T201

import argparse
import datetime
import json
import logging
import os
import sys
from collections import defaultdict
from functools import cache
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

import boto3
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from mypy_boto3_ce import CostExplorerClient
else:
    CostExplorerClient = object

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Constants for magic numbers
MIN_GROUP_KEYS_COUNT = 2


def get_project_resources(
    project_id: str, start_date: datetime.date, end_date: datetime.date
) -> dict[str, dict[str, list[dict]]]:
    """Get resources for a specific project grouped by account, then by service category and VPC."""
    # Get itemized data for all projects with account and resource details
    project_data = get_projectid_itemized_totals_with_accounts(start_date, end_date)

    # Find the specific project
    groupby_tag_name = os.environ.get("GROUPBY_TAG_NAME", "ProjectId")
    project_key = f"{groupby_tag_name}${project_id}"
    if project_key not in project_data:
        logger.warning(f"Project {project_id} not found in cost data")
        return {}

    # Get account mapping for display names
    account_mapping = get_account_mapping()

    # Group by account first, then by category/VPC
    accounts_data = {}

    for account_id, services in project_data[project_key].items():
        account_name = account_mapping.get(account_id, f"Account-{account_id}")
        account_key = f"Account: {account_name} ({account_id})"

        # Group services by category and VPC for this account
        resources_by_category = defaultdict(list)
        vpc_resources = defaultdict(list)

        # Process services, potentially including EC2 - Other breakdown
        final_services = services
        ec2_other_cost = services.get("EC2 - Other", 0)
        if ec2_other_cost > 0:
            logger.info(
                f"Found EC2 - Other costs in {account_name}: ${ec2_other_cost:.2f}, attempting to break down..."
            )
            ec2_other_breakdown = get_ec2_other_breakdown_for_account(project_id, account_id, start_date, end_date)
            # Remove the generic "EC2 - Other" and replace with breakdown
            if ec2_other_breakdown:
                # Create updated services dict with EC2 breakdown
                final_services = dict(services)
                del final_services["EC2 - Other"]
                final_services.update(ec2_other_breakdown)

        for service_name, cost in final_services.items():
            if cost > 0:  # Only include services with actual cost
                resource_info = {
                    "service": service_name,
                    "cost": cost,
                    "currency": "USD",
                    "account_id": account_id,
                    "account_name": account_name,
                }

                # Check if this is a VPC-related service
                vpc_info = extract_vpc_info(service_name)
                if vpc_info:
                    vpc_key = f"VPC: {vpc_info['vpc_id']}" if vpc_info["vpc_id"] else "VPC: Unknown"
                    resource_info["vpc_id"] = vpc_info["vpc_id"]
                    resource_info["resource_type"] = vpc_info["resource_type"]
                    vpc_resources[vpc_key].append(resource_info)
                else:
                    # Categorize services (basic categorization)
                    category = categorize_service(service_name)
                    resources_by_category[category].append(resource_info)

        # Merge VPC resources with regular categories
        for vpc_key, vpc_services in vpc_resources.items():
            resources_by_category[vpc_key] = vpc_services

        # Sort resources within each category by cost (highest first)
        for category in resources_by_category:
            resources_by_category[category].sort(key=lambda x: x["cost"], reverse=True)

        accounts_data[account_key] = dict(resources_by_category)

    return accounts_data


def _get_project_account_costs(
    ce_client: CostExplorerClient,
    start_date: datetime.date,
    end_date: datetime.date,
    groupby_tag_name: str,
) -> dict[str, dict[str, float]]:
    """Get project costs grouped by account."""
    group_by = [{"Type": "TAG", "Key": groupby_tag_name}, {"Type": "DIMENSION", "Key": "LINKED_ACCOUNT"}]

    all_results = {"ResultsByTime": []}
    response = ce_client.get_cost_and_usage(
        TimePeriod={"Start": start_date.isoformat(), "End": end_date.isoformat()},
        Granularity="DAILY",
        GroupBy=group_by,
        Metrics=["UnblendedCost", "UsageQuantity"],
    )
    all_results["ResultsByTime"].extend(response["ResultsByTime"])

    # Handle paged responses
    while "NextPageToken" in response and response["NextPageToken"]:
        response = ce_client.get_cost_and_usage(
            TimePeriod={"Start": start_date.isoformat(), "End": end_date.isoformat()},
            Granularity="DAILY",
            GroupBy=group_by,
            Metrics=["UnblendedCost", "UsageQuantity"],
            NextPageToken=response["NextPageToken"],
        )
        all_results["ResultsByTime"].extend(response["ResultsByTime"])

    # Process results into project -> account -> total cost mapping
    project_accounts = defaultdict(lambda: defaultdict(float))
    for period in all_results["ResultsByTime"]:
        for group in period["Groups"]:
            if len(group["Keys"]) >= MIN_GROUP_KEYS_COUNT:
                project_id, account_id = group["Keys"]
                amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                project_accounts[project_id][account_id] += amount

    return dict(project_accounts)


def _get_project_service_costs(
    ce_client: CostExplorerClient,
    start_date: datetime.date,
    end_date: datetime.date,
    groupby_tag_name: str,
) -> dict[str, dict[str, float]]:
    """Get project costs grouped by service."""
    group_by_service = [{"Type": "TAG", "Key": groupby_tag_name}, {"Type": "DIMENSION", "Key": "SERVICE"}]

    response = ce_client.get_cost_and_usage(
        TimePeriod={"Start": start_date.isoformat(), "End": end_date.isoformat()},
        Granularity="DAILY",
        GroupBy=group_by_service,
        Metrics=["UnblendedCost", "UsageQuantity"],
    )
    all_results_services = {"ResultsByTime": [response["ResultsByTime"][0]]}

    # Handle paged responses for service data
    while "NextPageToken" in response and response["NextPageToken"]:
        response = ce_client.get_cost_and_usage(
            TimePeriod={"Start": start_date.isoformat(), "End": end_date.isoformat()},
            Granularity="DAILY",
            GroupBy=group_by_service,
            Metrics=["UnblendedCost", "UsageQuantity"],
            NextPageToken=response["NextPageToken"],
        )
        all_results_services["ResultsByTime"].extend(response["ResultsByTime"])

    # Get service details for each project
    project_services = defaultdict(lambda: defaultdict(float))
    for period in all_results_services["ResultsByTime"]:
        for group in period["Groups"]:
            if len(group["Keys"]) >= MIN_GROUP_KEYS_COUNT:
                project_id, service = group["Keys"]
                amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                project_services[project_id][service] += amount

    return dict(project_services)


def _distribute_services_across_accounts(
    project_accounts: dict[str, dict[str, float]],
    project_services: dict[str, dict[str, float]],
) -> dict[str, dict[str, dict[str, float]]]:
    """Distribute services across accounts proportionally."""
    project_account_services = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))

    for project_id, services in project_services.items():
        if project_id in project_accounts:
            total_project_cost = sum(project_accounts[project_id].values())

            if total_project_cost > 0:
                for account_id, account_cost in project_accounts[project_id].items():
                    account_proportion = account_cost / total_project_cost

                    for service_name, service_cost in services.items():
                        proportional_cost = service_cost * account_proportion
                        if proportional_cost > 0:
                            project_account_services[project_id][account_id][service_name] = proportional_cost

    return dict(project_account_services)


def get_projectid_itemized_totals_with_accounts(
    start_date: datetime.date, end_date: datetime.date
) -> dict[str, dict[str, dict[str, float]]]:
    """Get project itemized totals grouped by account from AWS Cost Explorer."""
    ce_client = boto3.client("ce")
    groupby_tag_name = os.environ.get("GROUPBY_TAG_NAME", "ProjectId")

    # Get project costs by account
    project_accounts = _get_project_account_costs(ce_client, start_date, end_date, groupby_tag_name)

    # Get project costs by service
    project_services = _get_project_service_costs(ce_client, start_date, end_date, groupby_tag_name)

    # Distribute services across accounts proportionally
    return _distribute_services_across_accounts(project_accounts, project_services)


def get_ec2_other_breakdown_for_account(
    project_id: str, account_id: str, start_date: datetime.date, end_date: datetime.date
) -> dict[str, float]:
    """Get detailed breakdown of EC2 - Other costs for a specific account using USAGE_TYPE dimension."""
    ce_client = boto3.client("ce")
    groupby_tag_name = os.environ.get("GROUPBY_TAG_NAME", "ProjectId")

    try:
        # Use SERVICE and USAGE_TYPE to break down EC2 - Other
        group_by = [{"Type": "DIMENSION", "Key": "SERVICE"}, {"Type": "DIMENSION", "Key": "USAGE_TYPE"}]

        # Filter specifically for the project, account, and EC2 - Other service
        filters = {
            "And": [
                {"Tags": {"Key": groupby_tag_name, "Values": [project_id]}},
                {"Dimensions": {"Key": "LINKED_ACCOUNT", "Values": [account_id]}},
                {"Dimensions": {"Key": "SERVICE", "Values": ["EC2 - Other"]}},
            ]
        }

        # Get cost data from AWS
        response = ce_client.get_cost_and_usage(
            TimePeriod={"Start": start_date.isoformat(), "End": end_date.isoformat()},
            Granularity="DAILY",
            GroupBy=group_by,
            Metrics=["UnblendedCost"],
            Filter=filters,
        )

        # Process results into usage type -> cost mapping
        usage_type_costs = defaultdict(float)
        for period in response["ResultsByTime"]:
            for group in period["Groups"]:
                if len(group["Keys"]) >= MIN_GROUP_KEYS_COUNT:
                    service, usage_type = group["Keys"]
                    if service == "EC2 - Other":
                        amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                        # Create a more descriptive name
                        detailed_name = categorize_ec2_other_usage_type(usage_type)
                        usage_type_costs[detailed_name] += amount

        return dict(usage_type_costs)

    except (ClientError, KeyError, ValueError, TypeError) as e:
        logger.warning(f"Failed to break down EC2 - Other costs for account {account_id}: {e}")
        return {}


@cache
def get_account_mapping() -> dict[str, str]:
    """Get account ID to name mapping from the accountid_mapping.json file."""
    try:
        # Look for the mapping file in the project root
        mapping_file = Path(__file__).parent.parent / "accountid_mapping.json"
        if mapping_file.exists():
            with mapping_file.open(encoding="utf-8") as f:
                mapping = json.load(f)
                logger.info(f"Successfully loaded account mapping with {len(mapping)} entries")
                return mapping
        else:
            logger.warning(f"Account mapping file not found at {mapping_file}")
            return {}
    except (OSError, json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Failed to load account mapping: {e}")
        return {}


def get_projectid_itemized_totals_with_resources(
    start_date: datetime.date, end_date: datetime.date
) -> dict[str, dict[str, float]]:
    """Get project itemized totals with detailed resource information from AWS Cost Explorer."""
    ce_client = boto3.client("ce")
    groupby_tag_name = os.environ.get("GROUPBY_TAG_NAME", "ProjectId")

    # Build the group by configuration (max 2 dimensions allowed by AWS)
    group_by = [{"Type": "TAG", "Key": groupby_tag_name}, {"Type": "DIMENSION", "Key": "SERVICE"}]

    # Get cost data from AWS
    all_results = {"ResultsByTime": []}
    response = ce_client.get_cost_and_usage(
        TimePeriod={"Start": start_date.isoformat(), "End": end_date.isoformat()},
        Granularity="DAILY",
        GroupBy=group_by,
        Metrics=["UnblendedCost", "UsageQuantity"],
    )
    all_results["ResultsByTime"].extend(response["ResultsByTime"])

    # Handle paged responses
    while "NextPageToken" in response and response["NextPageToken"]:
        response = ce_client.get_cost_and_usage(
            TimePeriod={"Start": start_date.isoformat(), "End": end_date.isoformat()},
            Granularity="DAILY",
            GroupBy=group_by,
            Metrics=["UnblendedCost", "UsageQuantity"],
            NextPageToken=response["NextPageToken"],
        )
        all_results["ResultsByTime"].extend(response["ResultsByTime"])

    # Process results into project -> service -> cost mapping
    project_services = defaultdict(lambda: defaultdict(float))
    for period in all_results["ResultsByTime"]:
        for group in period["Groups"]:
            if len(group["Keys"]) >= MIN_GROUP_KEYS_COUNT:
                project_id, service = group["Keys"]
                amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                project_services[project_id][service] += amount

    return dict(project_services)


def extract_vpc_info(service_name: str) -> dict[str, str] | None:
    """Extract VPC information from service name."""
    # VPC-related services (services that typically run within a VPC)
    vpc_services = {
        "Amazon Elastic Compute Cloud - Compute": "EC2 Instance",
        "Amazon Virtual Private Cloud": "VPC Service",
        "Amazon Elastic Block Store": "EBS Volume",
        "Elastic Load Balancing": "Load Balancer",
        "Amazon Relational Database Service": "RDS Instance",
        "Amazon ElastiCache": "Cache Node",
        "Amazon Elastic Container Service": "ECS Service",
        "Amazon Elastic Kubernetes Service": "EKS Service",
        "AWS Direct Connect": "Direct Connect",
        "Amazon ElasticSearch Service": "Elasticsearch",
    }

    # Check if this service is VPC-related
    if service_name in vpc_services:
        resource_type = vpc_services[service_name]

        # Since we don't have USAGE_TYPE, we can't determine specific VPC ID
        # Group VPC resources by service type for now
        vpc_id = f"VPC-{resource_type}"

        return {"vpc_id": vpc_id, "resource_type": resource_type, "usage_type": "N/A"}

    return None


def get_ec2_other_breakdown(project_id: str, start_date: datetime.date, end_date: datetime.date) -> dict[str, float]:
    """Get detailed breakdown of EC2 - Other costs using USAGE_TYPE dimension."""
    ce_client = boto3.client("ce")
    groupby_tag_name = os.environ.get("GROUPBY_TAG_NAME", "ProjectId")

    try:
        # Use SERVICE and USAGE_TYPE to break down EC2 - Other
        group_by = [{"Type": "DIMENSION", "Key": "SERVICE"}, {"Type": "DIMENSION", "Key": "USAGE_TYPE"}]

        # Filter specifically for the project and EC2 - Other service
        filters = {
            "And": [
                {"Tags": {"Key": groupby_tag_name, "Values": [project_id]}},
                {"Dimensions": {"Key": "SERVICE", "Values": ["EC2 - Other"]}},
            ]
        }

        # Get cost data from AWS
        response = ce_client.get_cost_and_usage(
            TimePeriod={"Start": start_date.isoformat(), "End": end_date.isoformat()},
            Granularity="DAILY",
            GroupBy=group_by,
            Metrics=["UnblendedCost"],
            Filter=filters,
        )

        # Process results into usage type -> cost mapping
        usage_type_costs = defaultdict(float)
        for period in response["ResultsByTime"]:
            for group in period["Groups"]:
                if len(group["Keys"]) >= MIN_GROUP_KEYS_COUNT:
                    service, usage_type = group["Keys"]
                    if service == "EC2 - Other":
                        amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                        # Create a more descriptive name
                        detailed_name = categorize_ec2_other_usage_type(usage_type)
                        usage_type_costs[detailed_name] += amount

        return dict(usage_type_costs)

    except (ClientError, KeyError, ValueError, TypeError) as e:
        logger.warning(f"Failed to break down EC2 - Other costs: {e}")
        return {}


def categorize_ec2_other_usage_type(usage_type: str) -> str:
    """Categorize EC2 - Other usage types into more readable descriptions."""
    # Common EC2 - Other usage type patterns and their meanings
    usage_type_mapping = {
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

    # Try to match usage type to known patterns
    for pattern, description in usage_type_mapping.items():
        if pattern.lower() in usage_type.lower():
            return f"{description} ({usage_type})"

    # If no match, return a generic description with the usage type
    return f"EC2 - Other ({usage_type})"


def extract_vpc_id_from_usage_type(usage_type: str) -> str | None:
    """Try to extract VPC ID from usage type string."""
    # AWS Cost Explorer typically doesn't include actual VPC IDs in usage types
    # This is a best-effort extraction based on common patterns

    # Look for VPC-related identifiers
    if "vpc-" in usage_type.lower():
        # Extract vpc-xxxxxxxx pattern
        import re

        vpc_match = re.search(r"vpc-[a-f0-9]{8,17}", usage_type.lower())
        if vpc_match:
            return vpc_match.group(0)

    # For most cases, we can't determine the specific VPC ID from Cost Explorer data
    # We'll group by region/availability zone instead
    if any(region in usage_type for region in ["us-east", "us-west", "eu-", "ap-"]):
        # Extract region information
        import re

        region_match = re.search(r"(us-east-\d|us-west-\d|eu-[a-z]+-\d|ap-[a-z]+-\d)", usage_type)
        if region_match:
            return f"Region-{region_match.group(1)}"

    return None


def get_projectid_itemized_totals(start_date: datetime.date, end_date: datetime.date) -> dict[str, dict[str, float]]:
    """Get project itemized totals from AWS Cost Explorer."""
    ce_client = boto3.client("ce")
    groupby_tag_name = os.environ.get("GROUPBY_TAG_NAME", "ProjectId")

    # Build the group by configuration
    group_by = [{"Type": "TAG", "Key": groupby_tag_name}, {"Type": "DIMENSION", "Key": "SERVICE"}]

    # Get cost data from AWS
    all_results = {"ResultsByTime": []}
    response = ce_client.get_cost_and_usage(
        TimePeriod={"Start": start_date.isoformat(), "End": end_date.isoformat()},
        Granularity="DAILY",
        GroupBy=group_by,
        Metrics=["UnblendedCost", "UsageQuantity"],
    )
    all_results["ResultsByTime"].extend(response["ResultsByTime"])

    # Handle paged responses
    while "NextPageToken" in response and response["NextPageToken"]:
        response = ce_client.get_cost_and_usage(
            TimePeriod={"Start": start_date.isoformat(), "End": end_date.isoformat()},
            Granularity="DAILY",
            GroupBy=group_by,
            Metrics=["UnblendedCost", "UsageQuantity"],
            NextPageToken=response["NextPageToken"],
        )
        all_results["ResultsByTime"].extend(response["ResultsByTime"])

    # Process results into project -> service -> cost mapping
    project_services = defaultdict(lambda: defaultdict(float))
    for period in all_results["ResultsByTime"]:
        for group in period["Groups"]:
            if len(group["Keys"]) >= MIN_GROUP_KEYS_COUNT:
                project_id, service = group["Keys"]
                amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                project_services[project_id][service] += amount

    return dict(project_services)


@cache
def get_tag_display_mapping() -> dict[str, str]:
    """Get tag display mapping from S3 or return empty dict."""
    mapping_s3_uri = os.environ.get("GROUPBY_TAG_DISPLAY_MAPPING_S3_URI")
    mapping = {}

    if mapping_s3_uri:
        try:
            s3_client = boto3.client("s3")
            # Parse S3 URI
            from urllib.parse import urlparse

            result = urlparse(mapping_s3_uri)
            bucket = result.netloc
            key = result.path[1:]  # removes leading slash

            logger.info(f"Retrieving {mapping_s3_uri}...")
            buffer = BytesIO()
            s3_client.download_fileobj(Bucket=bucket, Key=key, Fileobj=buffer)
            buffer.seek(0)
            contents = buffer.getvalue().decode("utf8")
            mapping = json.loads(contents)
            logger.info(f"Successfully loaded tag mapping with {len(mapping)} entries")
        except ClientError:
            logger.warning(f"Tag mapping file {mapping_s3_uri} not found, using empty mapping")
        except json.JSONDecodeError:
            logger.warning(f"Unable to decode {mapping_s3_uri} as JSON, using empty mapping")
        except (OSError, ValueError) as e:
            logger.warning(f"Error loading tag mapping: {e}, using empty mapping")
    else:
        logger.info("No GROUPBY_TAG_DISPLAY_MAPPING_S3_URI set, using empty mapping")

    return mapping


def categorize_service(service_name: str) -> str:
    """Categorize AWS service into broader categories."""
    service_categories = {
        "Compute": {
            "Amazon Elastic Compute Cloud - Compute",
            "AWS Lambda",
            "Amazon Elastic Container Service",
            "Amazon Elastic Kubernetes Service",
            "AWS Batch",
        },
        "Storage": {
            "Amazon Simple Storage Service",
            "Amazon Elastic Block Store",
            "Amazon Elastic File System",
            "AWS Backup",
        },
        "Database": {
            "Amazon Relational Database Service",
            "Amazon DynamoDB",
            "Amazon ElastiCache",
            "Amazon Redshift",
            "Amazon DocumentDB",
        },
        "Networking": {
            "Amazon Virtual Private Cloud",
            "Amazon CloudFront",
            "Amazon Route 53",
            "AWS Direct Connect",
            "Elastic Load Balancing",
        },
        "Monitoring": {"Amazon CloudWatch", "AWS X-Ray", "AWS CloudTrail"},
        "API Services": {"Amazon API Gateway"},
    }

    for category, services in service_categories.items():
        if service_name in services:
            return category

    return "Other"


def display_project_details(
    project_id: str, resources: dict[str, dict[str, list[dict]]], project_name: str = None
) -> None:
    """Display project details in a formatted way with account breakdown."""
    display_name = project_name if project_name else "UNDEFINED"

    print("\n=== Project Details ===")
    print(f"Project ID: {project_id}")
    print(f"Project Name: {display_name}")
    today = datetime.datetime.now(datetime.UTC).date()
    print(f"Date Range: {today.replace(day=1)} to {today}")

    if not resources:
        print("\nNo resources found for this project in the current billing period.")
        return

    # Calculate total cost across all accounts
    total_cost = 0.0
    for account_categories in resources.values():
        for category_resources in account_categories.values():
            for resource in category_resources:
                total_cost += resource["cost"]

    print(f"Total Cost: ${total_cost:.2f} USD")
    print(f"Accounts: {len(resources)}")

    # Display resources grouped by account
    for account_key, account_categories in sorted(resources.items()):
        # Calculate account total
        account_total = 0.0
        for category_resources in account_categories.values():
            for resource in category_resources:
                account_total += resource["cost"]

        print(f"\n{'=' * 80}")
        print(f"{account_key} - Total: ${account_total:.2f} USD")
        print(f"{'=' * 80}")

        if not account_categories:
            print("  No resources found for this account.")
            continue

        # Display categories within this account
        for category, category_resources in sorted(account_categories.items()):
            category_total = sum(resource["cost"] for resource in category_resources)
            print(f"\n  {category} (${category_total:.2f} USD):")
            print(f"  {'-' * (len(category) + 20)}")

            for resource in category_resources:
                print(f"    • {resource['service']}: ${resource['cost']:.2f} {resource['currency']}")


def get_all_project_ids(start_date: datetime.date, end_date: datetime.date) -> list[str]:
    """Get all project IDs that have costs in the given period."""
    project_data = get_projectid_itemized_totals(start_date, end_date)
    groupby_tag_name = os.environ.get("GROUPBY_TAG_NAME", "ProjectId")

    project_ids = []
    for project_key in project_data:
        # Extract project ID from the key (format: "ProjectId$actual-project-id")
        if project_key.startswith(f"{groupby_tag_name}$"):
            project_id = project_key[len(f"{groupby_tag_name}$") :]
            if project_id:  # Skip empty project IDs
                project_ids.append(project_id)

    return sorted(project_ids)


def list_project_ids() -> None:
    """List all project IDs with their names, sorted by project name."""
    try:
        # Get current month date range
        today = datetime.datetime.now(datetime.UTC).date()
        start_date = today.replace(day=1)
        end_date = today

        logger.info(f"Fetching project IDs for date range: {start_date} to {end_date}")

        # Get all project IDs
        project_ids = get_all_project_ids(start_date, end_date)

        if not project_ids:
            print("No project IDs found for the current billing period.")
            return

        # Get project name mapping
        tag_mapping = get_tag_display_mapping()

        # Create list of tuples (project_name, project_id) for sorting by name
        project_list = []
        for project_id in project_ids:
            project_name = tag_mapping.get(project_id, "UNDEFINED")
            project_list.append((project_name, project_id))

        # Sort by project name (first element of tuple)
        project_list.sort(key=lambda x: x[0])

        print(f"\n=== Project IDs ({len(project_list)} found) ===")
        print(f"Date Range: {start_date} to {end_date}")
        print("Sorted by project name")
        print("-" * 60)

        for project_name, project_id in project_list:
            print(f"{project_id:<40} | {project_name}")

    except (ClientError, OSError, ValueError):
        logger.exception("Error listing project IDs")
        sys.exit(1)


def main() -> None:
    """Main function to handle CLI arguments and execute the script."""
    parser = argparse.ArgumentParser(
        description="Get project details with resources grouped by category",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python get_project_details.py --project-id 12345
  python get_project_details.py --project-id abc-def-ghi --log-level DEBUG
  python get_project_details.py list-projectids
        """,
    )

    # Create subparsers for different commands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Subparser for project details command (default behavior)
    details_parser = subparsers.add_parser(
        "details", help="Get project details (default command)", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    details_parser.add_argument("--project-id", required=True, help="Project ID to get details for")

    # Subparser for list-projectids command
    subparsers.add_parser("list-projectids", help="List all project IDs with their names")

    # Global arguments
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: INFO)",
    )

    # For backward compatibility, also accept --project-id at top level
    parser.add_argument("--project-id", help="Project ID to get details for (backward compatibility)")

    args = parser.parse_args()

    # Update logging level if specified
    if args.log_level != "INFO":
        logging.getLogger().setLevel(getattr(logging, args.log_level))

    try:
        # Handle different commands
        if args.command == "list-projectids":
            list_project_ids()
        elif args.command == "details":
            if not args.project_id:
                parser.error("--project-id is required for details command")

            # Get current month date range
            today = datetime.datetime.now(datetime.UTC).date()
            start_date = today.replace(day=1)
            end_date = today

            logger.info(f"Getting project details for project ID: {args.project_id}")
            logger.info(f"Date range: {start_date} to {end_date}")

            # Get project resources
            resources = get_project_resources(args.project_id, start_date, end_date)

            # Get project name mapping
            tag_mapping = get_tag_display_mapping()
            project_name = tag_mapping.get(args.project_id)

            # Display results
            display_project_details(args.project_id, resources, project_name)
        # Backward compatibility: if no command specified but --project-id given
        elif args.project_id:
            # Get current month date range
            today = datetime.datetime.now(datetime.UTC).date()
            start_date = today.replace(day=1)
            end_date = today

            logger.info(f"Getting project details for project ID: {args.project_id}")
            logger.info(f"Date range: {start_date} to {end_date}")

            # Get project resources
            resources = get_project_resources(args.project_id, start_date, end_date)

            # Get project name mapping
            tag_mapping = get_tag_display_mapping()
            project_name = tag_mapping.get(args.project_id)

            # Display results
            display_project_details(args.project_id, resources, project_name)
        else:
            parser.print_help()
            sys.exit(1)

    except (ClientError, OSError, ValueError):
        logger.exception("Error occurred")
        sys.exit(1)


if __name__ == "__main__":
    main()
