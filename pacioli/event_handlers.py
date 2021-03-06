"""
Defines the function called on the registered events in the 'zappa_settings.json' file.
"""
import datetime
import json
import logging
import sys
from pathlib import Path

from .functions import (
    check_phantomjs,
    generate_daily_chart_image,
    get_projecttotals_message_blocks,
    prepare_daily_chart_figure,
    prepare_daily_pie_chart_figure,
)
from .post import SlackPostManager
from .settings import SLACK_CHANNEL_NAME

DEFAULT_ACCOUNTID_MAPPING_FILENAME = "accountid_mapping.json"
DEFAULT_ACCOUNTID_MAPPING_FILEPATH = Path(__file__).resolve().parent.parent / DEFAULT_ACCOUNTID_MAPPING_FILENAME

logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(asctime)s [%(levelname)s] (%(name)s) %(funcName)s: %(message)s")
logging.getLogger("botocore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def post_daily_chart(event, context) -> None:
    """
    Handle the lambda event, create chart, chart image and post to slack.
    """
    check_phantomjs()
    now = datetime.datetime.now()

    accountid_mapping = None
    if DEFAULT_ACCOUNTID_MAPPING_FILEPATH.exists():
        with DEFAULT_ACCOUNTID_MAPPING_FILEPATH.open("r", encoding="utf8") as mapping:
            accountid_mapping = json.loads(mapping.read())

    logger.info("creating daily chart...")
    chart_figure, current_cost, previous_cost = prepare_daily_chart_figure(now, accountid_mapping)
    percentage_change = round((current_cost / previous_cost - 1.0) * 100, 1)

    logger.info("creating pie chart...")
    pie_figure, project_totals = prepare_daily_pie_chart_figure(now)

    logger.info("converting chart to image (png)...")
    daily_chart_image_object = generate_daily_chart_image(chart_figure)
    pie_chart_image_object = generate_daily_chart_image(pie_figure)

    logger.info("posting image to slack...")
    slack = SlackPostManager()

    slack.post_image_to_channel(
        channel_name=SLACK_CHANNEL_NAME,
        title=f"AWS Cost {now.month}/{now.day} ${round(current_cost, 2)} ({percentage_change}%)",
        image_object=daily_chart_image_object,
    )
    logger.info("posted: daily chart")

    slack.post_image_to_channel(
        channel_name=SLACK_CHANNEL_NAME, title=f"AWS Cost ProjectId/Service {now.month}/{now.day}", image_object=pie_chart_image_object
    )
    logger.info("posted: pie chart")

    title, project_totals_blocks = get_projecttotals_message_blocks(project_totals)
    logger.info("posting project_totals_message to slack...")
    logger.debug(project_totals_blocks)
    slack.post_message_to_channel(channel_name=SLACK_CHANNEL_NAME, message=title, blocks=project_totals_blocks)
    logger.info("posted: project_totals_message")

    logger.info("posted!")
