"""Defines the function called on the registered events in the 'zappa_settings.json' file."""

import datetime
import logging
import pprint
import sys
from pathlib import Path

from pacioli.functions import (
    get_accounttotals_message_blocks,
    get_projecttotals_message_blocks,
    get_topn_projectservices_message_blocks,
)
from pacioli.managers import ReportManager
from pacioli.reporting.slack import SlackPostManager
from pacioli.settings import DISPLAY_TIMEZONE, LOG_LEVEL, PROJECTSERVICES_TOPN, SLACK_CHANNEL_NAME

DEFAULT_ACCOUNTID_MAPPING_FILENAME = "accountid_mapping.json"
DEFAULT_ACCOUNTID_MAPPING_FILEPATH = Path(__file__).resolve().parent.parent.parent / DEFAULT_ACCOUNTID_MAPPING_FILENAME

logging.basicConfig(
    stream=sys.stdout, level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] (%(name)s) %(funcName)s: %(message)s"
)
logging.getLogger("botocore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def post_status(event: dict, _context: dict) -> None:
    """Generate cost reports and post results to slack."""
    post_to_slack = event.get("post_to_slack", True)
    logger.debug(f"post_to_slack={post_to_slack}")
    now = datetime.datetime.now(datetime.UTC)
    display_datetime = now.astimezone(DISPLAY_TIMEZONE).strftime("%m/%d %H:%M (%Z)")
    rm = ReportManager(generation_datetime=now)
    slack = SlackPostManager()

    # prepare accounts report
    account_totals = rm.generate_accounts_report()
    logger.debug("rm.generate_accounts_report() account_totals:")
    logger.debug(pprint.pformat(account_totals, indent=4))
    title, account_totals_blocks = get_accounttotals_message_blocks(account_totals, display_datetime)
    logger.debug("account_totals_blocks:")
    logger.debug(pprint.pformat(account_totals_blocks, indent=4))
    if post_to_slack:
        logger.info("posting account_totals_blocks to slack...")
        slack.post_message_to_channel(channel_name=SLACK_CHANNEL_NAME, message=title, blocks=account_totals_blocks)
        logger.info("posting account_totals_blocks to slack... DONE")

    # prepare projects report
    tax = rm.get_period_total_tax()
    project_totals = rm.generate_projectid_report()
    logger.debug("rm.generate_projectid_report() project_totals:")
    logger.debug(pprint.pformat(project_totals, indent=4))
    title, project_totals_blocks = get_projecttotals_message_blocks(project_totals, display_datetime, tax=tax)
    logger.debug("project_totals_blocks:")
    logger.debug(pprint.pformat(project_totals_blocks, indent=4))
    if post_to_slack:
        logger.info("posting project_totals_blocks to slack...")
        slack.post_message_to_channel(channel_name=SLACK_CHANNEL_NAME, message=title, blocks=project_totals_blocks)
        logger.info("posting project_totals_blocks to slack... DONE")

    # prepare top N projects breakdown report
    project_services = rm.generate_projectid_itemized_report()
    logger.debug("rm.generate_projectid_itemized_report() project_services:")
    logger.debug(pprint.pformat(project_services, indent=4))
    title, projectservice_totals_blocks = get_topn_projectservices_message_blocks(
        project_services, display_datetime, topn=PROJECTSERVICES_TOPN
    )
    logger.debug("projectservice_totals_blocks:")
    logger.debug(pprint.pformat(projectservice_totals_blocks, indent=4))
    if post_to_slack:
        logger.info("posting projectservice_totals_blocks to slack ...")
        slack.post_message_to_channel(
            channel_name=SLACK_CHANNEL_NAME, message=title, blocks=projectservice_totals_blocks
        )
        logger.info("posting projectservice_totals_blocks to slack ... DONE")
