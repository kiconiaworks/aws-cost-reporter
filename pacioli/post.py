"""
Perform actions necessary for interfacing with SLACK.
"""

import urllib.parse
from typing import BinaryIO, Optional

from slack_sdk import WebClient

from . import settings
from .exceptions import SlackChannelError


class SlackPostManager:
    """Main class for interfacing with Slack."""

    def __init__(self, token: str = settings.SLACK_TOKEN):
        self.sc = WebClient(token=token)

    def _get_channel_id(self, channel_name: str):
        """
        Obtain the channel_id given the channel_name.
        """
        # get channel id for channel name
        channel_id = None
        channel_query_response = self.sc.conversations_list(exclude_archived=True)
        for channel_info in channel_query_response["channels"]:
            if channel_info["name"] == channel_name:
                channel_id = channel_info["id"]
                break
        if not channel_id:
            raise SlackChannelError(f'"{channel_name}" not found!')

        return channel_id

    def post_message_to_channel(
        self, channel_name: str = settings.SLACK_CHANNEL_NAME, message: str = settings.SLACK_TEST_MESSAGE, blocks: Optional[list] = None
    ) -> None:
        """
        Post a text message as the defined bot to the given channel.
        """
        channel_id = self._get_channel_id(channel_name)
        kwargs = {"username": settings.SLACK_BOT_NAME, "icon_url": settings.SLACK_BOT_ICONURL, "text": message}
        if blocks:
            kwargs["blocks"] = blocks

        self.sc.chat_postMessage(channel=channel_id, **kwargs)

    def post_image_to_channel(self, channel_name: str, image_object: BinaryIO, title: str = "Test Upload") -> None:
        """
        Post an Image to a given channel.
        """
        channel_id = self._get_channel_id(channel_name)

        self.sc.files_upload(
            channels=channel_id,
            file=image_object.read(),
            title=title,
        )
