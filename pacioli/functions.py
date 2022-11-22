"""
Contains main functions for performing collection and generation of charts for posting to slack.
"""
import datetime
import json
import logging
from io import BytesIO
from operator import itemgetter
from pathlib import Path
from typing import Dict, Optional, Tuple

from . import settings
from .aws import S3_CLIENT, parse_s3_uri

logger = logging.getLogger(__name__)

DEFAULT_ACCOUNTID_MAPPING_FILENAME = "accountid_mapping.json"
DEFAULT_ACCOUNTID_MAPPING_FILEPATH = Path(__file__).resolve().parent.parent.parent / DEFAULT_ACCOUNTID_MAPPING_FILENAME


class ImageFormatError(ValueError):
    """Exception used when an unsupported Image format is used/given."""

    pass


def datestr2datetime(date_str) -> datetime.datetime:
    """Convert YYYY-MM-DD to a python datetime object."""
    return datetime.datetime.strptime(date_str, "%Y-%m-%d")


def get_month_starts(current_datetime: Optional[datetime.datetime] = None) -> Tuple[datetime.date, datetime.date, datetime.date]:
    """
    Calculate the `current` month start date and `previous` month start date from the given current datetime object.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
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
    """
    mapping_s3_uri is a JSON file that maps the Billing GroupBy Key to the desired display value.
    """
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
            except json.JSONDecodeError as e:
                logger.exception(e)
                logger.error(f"retrieving {mapping_s3_uri} ... ERROR")
                logger.error(f"Unable to decode {mapping_s3_uri} content as JSON: {contents}")
        except Exception as e:
            logger.exception(e)
            logger.warning(f"{mapping_s3_uri} not found!")
            logger.error(f"retrieving {mapping_s3_uri} ... ERROR")
    return mapping


def get_projecttotals_message_blocks(projects: list[dict]) -> Tuple[str, list]:
    """
    Process project totals into Slack formatted blocks.

    project_totals:

        {
            PROJECT_ID (str): PROJECT_TOTAL (float),
            ...
        }

    """
    # https://app.slack.com/block-kit-builder/
    title = "プロジェクトごと（月合計）"
    divider_element = {"type": "divider"}
    json_formatted_message = [{"type": "section", "text": {"type": "mrkdwn", "text": title}}, divider_element]

    dollar_emoji = ":heavy_dollar_sign:"
    total = sum(p["current_cost"] for p in projects)
    null_project_ids = ("nothing_project_tag", "")
    for project_info in projects:
        project_total = project_info["current_cost"]
        project_name = project_info["name"]
        project_id = project_info["id"]
        if project_id in null_project_ids:
            project_name = "ProjectIdタグなしのリソース費用"
        multiplier = int(5 * (project_total / total))
        dollar_emojis = "-"
        if int(project_total) > 0:
            dollar_emojis = dollar_emoji * (multiplier + 1)
        direction = ""
        change = project_info["percentage_change"]
        if change > 0:
            direction = "+"
        project_display_name = f"{project_name} ({project_id}) {direction}{change}%"
        project_section = {
            "type": "section",
            "text": {"text": project_display_name, "type": "mrkdwn"},
            "fields": [{"type": "mrkdwn", "text": dollar_emojis}, {"type": "mrkdwn", "text": f"${project_total:15.2f}"}],
        }
        json_formatted_message.append(project_section)
        json_formatted_message.append(divider_element)
    return title, json_formatted_message


def get_accountid_mapping() -> dict:
    """
    Get the accountid mapping dictionary
    """
    accountid_mapping = {}
    if DEFAULT_ACCOUNTID_MAPPING_FILEPATH.exists():
        with DEFAULT_ACCOUNTID_MAPPING_FILEPATH.open("r", encoding="utf8") as mapping:
            accountid_mapping = json.loads(mapping.read())
    return accountid_mapping
