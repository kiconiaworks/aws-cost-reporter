"""
Defines the function called on the registered events in the 'zappa_settings.json' file.
"""
import datetime
import json
import logging
import lzma
import os
import sys
from operator import itemgetter
from pathlib import Path
from typing import Dict, Tuple

from .functions import generate_daily_chart_image, prepare_daily_chart_figure, prepare_daily_pie_chart_figure
from .post import SlackPostManager
from .settings import BOKEH_PHANTOMJS_PATH, BOKEH_PHANTOMJSXZ_PATH, SLACK_CHANNEL_NAME

DEFAULT_ACCOUNTID_MAPPING_FILENAME = "accountid_mapping.json"
DEFAULT_ACCOUNTID_MAPPING_FILEPATH = Path(__file__).resolve().parent.parent / DEFAULT_ACCOUNTID_MAPPING_FILENAME

logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(asctime)s [%(levelname)s] (%(name)s) %(funcName)s: %(message)s")
logging.getLogger("botocore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def _check_phantomjs(filepath: str = BOKEH_PHANTOMJS_PATH) -> Path:
    """check if phantomjs binary exists, if not decompress"""
    p = Path(filepath)
    if not p.exists():
        logger.debug(f"uncompressing ({BOKEH_PHANTOMJSXZ_PATH}) -> {p} ...")
        compressed_filepath = Path(BOKEH_PHANTOMJSXZ_PATH)
        assert compressed_filepath.exists()
        # uncompress file into
        with p.open("wb") as uncompressed, compressed_filepath.open("rb") as compressed:
            uncompressed.write(lzma.LZMAFile(compressed).read())
        assert p.exists()
        os.chmod(str(p), 0o755)
        logger.debug(f"uncompressing ({BOKEH_PHANTOMJSXZ_PATH}) -> {p} ... COMPLETE!")
    return p


def _get_projecttotals_message_blocks(project_totals: Dict[str, float]) -> Tuple[str, list]:
    # https://app.slack.com/block-kit-builder/
    title = "プロジェクトごと（月合計）"
    divider_element = {"type": "divider"}
    json_formatted_message = [{"type": "section", "text": {"type": "mrkdwn", "text": title}}, divider_element]

    dollar_emoji = ":heavy_dollar_sign:"
    total = sum(project_totals.values())
    null_project_id = "nothing_project_tag"
    for project_id, project_total in sorted(project_totals.items(), key=itemgetter(1), reverse=True):
        if project_id == null_project_id:
            project_id = "ProjectIdタグなしのリソース費用"
        multiplier = int(5 * (project_total / total))
        dollar_emojis = "-"
        if int(project_total) > 0:
            dollar_emojis = dollar_emoji * (multiplier + 1)
        project_section = {
            "type": "section",
            "text": {"text": project_id, "type": "mrkdwn"},
            "fields": [{"type": "mrkdwn", "text": dollar_emojis}, {"type": "mrkdwn", "text": f"${project_total:15.2f}"}],
        }
        json_formatted_message.append(project_section)
        json_formatted_message.append(divider_element)
    return title, json_formatted_message


def post_daily_chart(event, context) -> None:
    """
    Handle the lambda event, create chart, chart image and post to slack.
    """
    _check_phantomjs()
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

    title, project_totals_blocks = _get_projecttotals_message_blocks(project_totals)
    logger.info("posting project_totals_message to slack...")
    logger.debug(project_totals_blocks)
    slack.post_message_to_channel(channel_name=SLACK_CHANNEL_NAME, message=title, blocks=project_totals_blocks)
    logger.info("posted: project_totals_message")

    logger.info("posted!")
