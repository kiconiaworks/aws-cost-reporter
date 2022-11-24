"""
Define package wide settings and handle environment variable defined settings.
"""
import datetime
import logging
import os

from .exceptions import SlackError

DEFAULT_LOG_LEVEL = "INFO"
RAW_LOG_LEVEL = os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL)
if not hasattr(logging, RAW_LOG_LEVEL):
    raise ValueError(f"Invalid LOG_LEVEL({RAW_LOG_LEVEL}), must be: INFO, DEBUG, WARNING, ERROR, CRITICAL")

LOG_LEVEL = getattr(logging, RAW_LOG_LEVEL)

GROUPBY_TAG_NAME = os.environ.get("GROUPBY_TAG_NAME", "ProjectId")
GROUPBY_TAG_DISPLAY_MAPPING_S3_URI = os.getenv("GROUPBY_TAG_DISPLAY_MAPPING_S3_URI", None)

DEFAULT_SLACK_CHANNEL_NAME = "cost_management"
SLACK_CHANNEL_NAME = os.getenv("SLACK_CHANNEL_NAME", DEFAULT_SLACK_CHANNEL_NAME)

SLACK_TOKEN = os.getenv("SLACK_API_TOKEN", None)
if not SLACK_TOKEN:
    raise SlackError('Required "SLACK_API_TOKEN" environment variable not set!')

SLACK_BOT_NAME = os.getenv("SLACK_BOT_NAME", "pacioli")
SLACK_BOT_ICONURL = os.getenv("SLACK_BOT_ICONURL", "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2a/Pacioli.jpg/174px-Pacioli.jpg")

DEFAULT_SLACK_TEST_MESSAGE = ":fire: :heavy_dollar_sign: fire: Accounting Rules :fire: :heavy_dollar_sign: :fire:"
SLACK_TEST_MESSAGE = os.getenv("SLACK_TEST_MESSAGE", DEFAULT_SLACK_TEST_MESSAGE)

# AWS/BOTO3 Configuration
AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-west-2")

DEFAULT_S3_SERVICE_ENDPOINT = f"https://s3.{AWS_DEFAULT_REGION}.amazonaws.com"
AWS_SERVICE_ENDPOINTS = {"s3": os.getenv("S3_SERVICE_ENDPOINT", DEFAULT_S3_SERVICE_ENDPOINT)}

DEFAULT_PROJECTSERVICES_TOPN = 10
PROJECTSERVICES_TOPN = int(os.getenv("PROJECTSERVICES_TOPN", DEFAULT_PROJECTSERVICES_TOPN))

DEFAULT_UTC_OFFSET = 9
UTC_OFFSET = float(os.getenv("UTC_OFFSET", DEFAULT_UTC_OFFSET))

DISPLAY_TIMEZONE = datetime.timezone(datetime.timedelta(hours=UTC_OFFSET))
