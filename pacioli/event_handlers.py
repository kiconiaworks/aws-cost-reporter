"""
Defines the function called on the registered events in the 'zappa_settings.json' file.
"""
import os
import sys
import logging
import datetime
import json
from pathlib import Path

from .functions import prepare_daily_chart_figure, generate_daily_chart_image
from .post import SlackPostManager

DEFAULT_ACCOUNTID_MAPPING_FILENAME = 'accountid_mapping.json'
DEFAULT_ACCOUNTID_MAPPING_FILEPATH = Path(__file__).resolve().parent.parent / DEFAULT_ACCOUNTID_MAPPING_FILENAME

DEFAULT_SLACK_CHANNEL_NAME = 'cost_management'
SLACK_CHANNEL_NAME = os.getenv('SLACK_CHANNEL_NAME', DEFAULT_SLACK_CHANNEL_NAME)

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] (%(name)s) %(funcName)s: %(message)s'
)

logger = logging.getLogger(__name__)


def post_daily_chart(event, context) -> None:
    """
    Handle the lambda event, create chart, chart image and post to slack
    """
    now = datetime.datetime.now()

    accountid_mapping = None
    if DEFAULT_ACCOUNTID_MAPPING_FILEPATH.exists():
        with DEFAULT_ACCOUNTID_MAPPING_FILEPATH.open('r', encoding='utf8') as mapping:
            accountid_mapping = json.loads(mapping.read())

    logger.info('creating daily chart...')
    chart_figure = prepare_daily_chart_figure(now, accountid_mapping)

    logger.info('converting chart to image (png)...')
    image_object = generate_daily_chart_image(chart_figure)

    logger.info('posting image to slack...')
    slack = SlackPostManager()
    slack.post_image_to_channel(
        channel_name=SLACK_CHANNEL_NAME,
        title=f'AWS Cost {now.month}/{now.day}',
        image_object=image_object
    )
    logger.info('posted!')
