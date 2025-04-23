"""Contains main functions for performing collection and generation of charts for posting to slack."""

import datetime
import json
import logging
from io import BytesIO
from pathlib import Path

from . import settings
from .aws import S3_CLIENT, parse_s3_uri
from .definitions import AccountCostChange, ProjectCostChange, ProjectServicesCost

logger = logging.getLogger(__name__)

DEFAULT_ACCOUNTID_MAPPING_FILENAME = "accountid_mapping.json"
DEFAULT_ACCOUNTID_MAPPING_FILEPATH = Path(__file__).resolve().parent.parent / DEFAULT_ACCOUNTID_MAPPING_FILENAME


def datestr2datetime(date_str: str) -> datetime.datetime:
    """Convert YYYY-MM-DD to a python datetime object."""
    return datetime.datetime.strptime(date_str, "%Y-%m-%d").astimezone(datetime.UTC)


def get_month_starts(
    current_datetime: datetime.datetime | None = None,
) -> tuple[datetime.date, datetime.date, datetime.date]:
    """Calculate `current` month start date and `previous` month start date from the given current datetime object."""
    now = datetime.datetime.now(datetime.UTC)
    if not current_datetime:
        current_datetime = now

    # get nearest FULL day
    most_recent_full_date = current_datetime.date()
    if current_datetime.day > 1:
        most_recent_full_date = current_datetime.date() - datetime.timedelta(days=1)

    current_month_start = datetime.date(most_recent_full_date.year, most_recent_full_date.month, 1)
    previous_month_start = (current_month_start.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
    return most_recent_full_date, current_month_start, previous_month_start


def get_tag_display_mapping(mapping_s3_uri: str = settings.GROUPBY_TAG_DISPLAY_MAPPING_S3_URI) -> dict:
    """mapping_s3_uri is a JSON file that maps the Billing GroupBy Key to the desired display value."""
    mapping = {}
    if mapping_s3_uri:
        logger.info(f"retrieving {mapping_s3_uri} ...")
        bucket, key = parse_s3_uri(mapping_s3_uri)
        try:
            buffer = BytesIO()
            S3_CLIENT.download_fileobj(Bucket=bucket, Key=key, Fileobj=buffer)
            contents = buffer.getvalue().decode("utf8")
            logger.info(f"retrieving {mapping_s3_uri} ... SUCCESS")
            # load contents to mapping dictionary
            try:
                logger.info(f"loading {mapping_s3_uri} ... ")
                mapping = json.loads(contents)
                logger.info(f"loading {mapping_s3_uri} ... SUCCESS")
            except json.JSONDecodeError:
                logger.exception(f"retrieving {mapping_s3_uri} ... ERROR")
                logger.exception(f"Unable to decode {mapping_s3_uri} content as JSON: {contents}")
        except Exception:
            logger.warning(f"{mapping_s3_uri} not found!")
            logger.exception(f"retrieving {mapping_s3_uri} ... ERROR")
    return mapping


def get_accounttotals_message_blocks(
    accounts: list[AccountCostChange], display_datetime: str | None = ""
) -> tuple[str, list]:
    """Prepare account totals message blocks for post to slack"""
    dollar_emoji = ":heavy_dollar_sign:"
    previous_total = sum(a.previous_cost for a in accounts)
    current_total = sum(a.current_cost for a in accounts)
    total_change = round((current_total / previous_total - 1.0) * 100, 1)
    direction = ""
    if total_change > 0:
        direction = "+"
    title = f"*管理アカウント（月合計）{display_datetime}* ${current_total:15.2f} {direction}{total_change}%"
    divider_element = {"type": "divider"}
    json_formatted_message = [{"type": "section", "text": {"type": "mrkdwn", "text": title}}, divider_element]
    for account_info in accounts:
        name = account_info.name
        account_id = account_info.id
        direction = ""
        change = account_info.percentage_change
        if change > 0:
            direction = "+"
        display_name = f"{name} ({account_id}) {direction}{change}%"
        account_total = account_info.current_cost
        multiplier = int(5 * (account_total / current_total))
        dollar_emojis = "-"
        if int(account_total) > 0:
            dollar_emojis = dollar_emoji * (multiplier + 1)
        section = {
            "type": "section",
            "text": {"text": display_name, "type": "mrkdwn"},
            "fields": [
                {"type": "mrkdwn", "text": dollar_emojis},
                {"type": "mrkdwn", "text": f"_${account_total:15.2f}_"},
            ],
        }
        json_formatted_message.append(section)
        json_formatted_message.append(divider_element)
    return title, json_formatted_message


def get_projecttotals_message_blocks(
    projects: list[ProjectCostChange], display_datetime: str | None = "", tax: float = 0.0
) -> tuple[str, list]:
    """Process project totals into Slack formatted blocks."""
    # https://app.slack.com/block-kit-builder/
    title = f"*プロジェクトごと（月合計）{display_datetime}*"
    divider_element = {"type": "divider"}
    json_formatted_message = [
        {"type": "section", "text": {"type": "mrkdwn", "text": title}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"_Tax: ${tax:.2f}_"}},
        divider_element,
    ]

    dollar_emoji = ":heavy_dollar_sign:"
    total = sum(p.current_cost for p in projects)
    null_project_ids = ("nothing_project_tag", "")
    for project_info in projects:
        project_total = project_info.current_cost
        project_name = project_info.name
        project_id = project_info.id
        if project_id in null_project_ids:
            logger.debug(f"project_id={project_id}")
            project_name = "ProjectIdタグなしのリソース費用"
            # subtract tax from tag-less
            logger.info(f"tax subtracted from tagless: {project_total} - {tax} = {project_total - tax}")
            project_total = project_total - tax

        multiplier = int(5 * (project_total / total))
        dollar_emojis = "-"
        if int(project_total) > 0:
            dollar_emojis = dollar_emoji * (multiplier + 1)
        change_display = "-"
        direction = ""
        change = project_info.percentage_change
        if change:
            if change > 0:
                direction = "+"
            change_display = f"{direction}{change}%"
        project_id_display = ""
        if project_id:
            project_id_display = f"({project_id})"
        project_display_name = f"{project_name} {project_id_display} {change_display}"
        project_section = {
            "type": "section",
            "text": {"text": project_display_name, "type": "mrkdwn"},
            "fields": [
                {"type": "mrkdwn", "text": dollar_emojis},
                {"type": "mrkdwn", "text": f"_${project_total:15.2f}_"},
            ],
        }
        json_formatted_message.append(project_section)
        json_formatted_message.append(divider_element)

    if len(json_formatted_message) > settings.JSON_MAX_LENGTH:
        logger.warning(
            f"len(json_formatted_message) {len(json_formatted_message) > settings.JSON_MAX_LENGTH} > "
            f"{settings.JSON_MAX_LENGTH}, truncating json_formatted_message!"
        )
        json_formatted_message = json_formatted_message[:50]
    return title, json_formatted_message


def get_topn_projectservices_message_blocks(
    project_services: list[ProjectServicesCost], display_datetime: str | None = "", topn: int | None = 5
) -> tuple[str, list]:
    """Prepare Top N Project Services message blocks for post to slack"""
    title = f"*プロジェクトサービス（月合計）Top {topn} {display_datetime}*"
    divider_element = {"type": "divider"}
    json_formatted_message = [{"type": "section", "text": {"type": "mrkdwn", "text": title}}, divider_element]
    null_project_ids = ("nothing_project_tag", "")
    for count, project_info in enumerate(project_services[:topn], start=1):
        project_name = project_info.name
        project_id = project_info.id
        if project_id in null_project_ids:
            logger.debug(f"project_id={project_id}")
            project_name = "ProjectIdタグなしのリソース費用"
        total_cost = project_info.total_cost
        project_id_display = ""
        if project_id:
            project_id_display = f"({project_id})"
        project_display_name = f"_*{count}. {project_name}* {project_id_display} ${total_cost:15.2f}_"

        project_fields = []
        for service_info in project_info.services:
            v = {"type": "mrkdwn", "text": f"_{service_info.name} ${service_info.cost:.2f}_"}
            project_fields.append(v)
        if len(project_fields) > settings.PROJECT_FIELDS_MAX_LENGTH:
            logger.warning(
                f"len(project_fields) {len(project_fields)} > {settings.PROJECT_FIELDS_MAX_LENGTH}, truncating..."
            )
            top9 = project_fields[:9]
            remaining = project_fields[9:]
            others_cost = 0
            for entry in remaining:
                # parse text to cost
                remaining_cost = float(entry["text"].split("$")[-1].replace("_", ""))
                others_cost += remaining_cost
            others = {"type": "mrkdwn", "text": f"_Others ${others_cost:.2f}_"}
            project_fields = top9
            project_fields.append(others)
        project_section = {
            "type": "section",
            "text": {"text": project_display_name, "type": "mrkdwn"},
            "fields": project_fields,
        }
        json_formatted_message.append(project_section)
        json_formatted_message.append(divider_element)
    return title, json_formatted_message


def get_accountid_mapping() -> dict:
    """Get the accountid mapping dictionary"""
    accountid_mapping = {}
    logger.debug(f"DEFAULT_ACCOUNTID_MAPPING_FILEPATH={DEFAULT_ACCOUNTID_MAPPING_FILEPATH}")
    logger.debug(f"DEFAULT_ACCOUNTID_MAPPING_FILEPATH.exists()={DEFAULT_ACCOUNTID_MAPPING_FILEPATH.exists()}")
    if DEFAULT_ACCOUNTID_MAPPING_FILEPATH.exists():
        accountid_mapping = json.loads(DEFAULT_ACCOUNTID_MAPPING_FILEPATH.read_text(encoding="utf8"))
    return accountid_mapping
