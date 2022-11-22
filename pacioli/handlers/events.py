"""
Defines the function called on the registered events in the 'zappa_settings.json' file.
"""
import datetime
import logging
import sys
from pathlib import Path

from ..functions import get_projecttotals_message_blocks
from ..managers import ReportManager
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
    rm = ReportManager(generation_datetime=now)

    logger.info("posting to slack...")
    slack = SlackPostManager()

    # prepare accounts report
    # TODO: finish!

    # prepare projects report
    project_totals = rm.generate_projectid_report()
    title, project_totals_blocks = get_projecttotals_message_blocks(project_totals)
    logger.info("posting project_totals_message to slack...")
    logger.debug(project_totals_blocks)
    slack.post_message_to_channel(channel_name=SLACK_CHANNEL_NAME, message=title, blocks=project_totals_blocks)
    logger.info("posted: project_totals_message")

    # prepare top N projects breakdown report
    # TODO: finish

    logger.info("posted!")
