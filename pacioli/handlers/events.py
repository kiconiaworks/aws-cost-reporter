"""
Defines the function called on the registered events in the 'zappa_settings.json' file.
"""
import datetime
import json
import logging
import sys
from pathlib import Path

from ..functions import get_month_starts, get_projecttotals_message_blocks
from ..managers import CostManager
from ..reporting.slack import SlackPostManager
from ..settings import SLACK_CHANNEL_NAME

DEFAULT_ACCOUNTID_MAPPING_FILENAME = "accountid_mapping.json"
DEFAULT_ACCOUNTID_MAPPING_FILEPATH = Path(__file__).resolve().parent.parent.parent / DEFAULT_ACCOUNTID_MAPPING_FILENAME

logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(asctime)s [%(levelname)s] (%(name)s) %(funcName)s: %(message)s")
logging.getLogger("botocore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def post_status(event, context) -> None:
    """
    Handle the lambda event, create chart, chart image and post to slack.
    """
    now = datetime.datetime.now()
    end, current_month_start, previous_month_start = get_month_starts(now)

    cm = CostManager()

    current_cost, previous_cost = cm.get_stats()
    percentage_change = round((current_cost / previous_cost - 1.0) * 100, 1)

    logger.info("Get project totals...")
    project_totals = cm.get_project_totals()

    logger.info("posting to slack...")
    slack = SlackPostManager()

    # slack.post_image_to_channel(
    #     channel_name=SLACK_CHANNEL_NAME,
    #     title=f"AWS Cost {now.month}/{now.day} ${round(current_cost, 2)} ({percentage_change}%)",
    #     image_object=daily_chart_image_object,
    # )
    # logger.info("posted: daily chart")

    # slack.post_image_to_channel(
    #     channel_name=SLACK_CHANNEL_NAME, title=f"AWS Cost ProjectId/Service {now.month}/{now.day}", image_object=pie_chart_image_object
    # )
    # logger.info("posted: pie chart")

    title, project_totals_blocks = get_projecttotals_message_blocks(project_totals)
    logger.info("posting project_totals_message to slack...")
    logger.debug(project_totals_blocks)
    slack.post_message_to_channel(channel_name=SLACK_CHANNEL_NAME, message=title, blocks=project_totals_blocks)
    logger.info("posted: project_totals_message")

    logger.info("posted!")
