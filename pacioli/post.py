"""
Perform actions necessary for interfacing with SLACK.
"""
import os
from typing import BinaryIO

from slackclient import SlackClient

SLACK_CHANNEL_NAME = os.getenv('SLACK_CHANNEL_NAME', 'cost_management')
SLACK_TOKEN = os.getenv('SLACK_API_TOKEN', None)
SLACK_BOT_NAME = os.getenv('SLACK_BOT_NAME', 'pacioli')
SLACK_BOT_ICONURL = os.getenv('SLACK_BOT_ICONURL', 'https://upload.wikimedia.org/wikipedia/commons/thumb/2/2a/Pacioli.jpg/174px-Pacioli.jpg')
DEFAULT_TEST_MESSAGE = ":fire: :heavy_dollar_sign::heavy_dollar_sign: :fire: Accounting Rules :fire: :heavy_dollar_sign::heavy_dollar_sign: :fire:"


class SlackError(Exception):
    """General Slack Error."""
    pass


class SlackChannelError(Exception):
    """Raise when Slack Channel not found."""
    pass


if not SLACK_TOKEN:
    raise SlackError('Required "SLACK_API_TOKEN" environment variable not set!')


class SlackPostManager:
    """Main class for interfacing with Slack."""

    def __init__(self, token: str = SLACK_TOKEN):
        self.sc = SlackClient(token)

    def _get_channel_id(self, channel_name: str):
        """
        Obtain the channel_id given the channel_name.
        """
        # get channel id for channel name
        channel_id = None
        channel_query_response = self.sc.api_call(
            'channels.list',
            exclude_archived=True
        )
        for channel_info in channel_query_response['channels']:
            if channel_info['name'] == channel_name:
                channel_id = channel_info['id']
                break
        if not channel_id:
            raise SlackChannelError(f'"{channel_name}" not found!')

        return channel_id

    def post_message_to_channel(self, channel_name=SLACK_CHANNEL_NAME, message=DEFAULT_TEST_MESSAGE) -> None:
        """
        Post a text message as the defined bot to the given channel.
        """
        channel_id = self._get_channel_id(channel_name)
        self.sc.api_call(
            "chat.postMessage",
            channel=channel_id,
            username=SLACK_BOT_NAME,
            icon_url=SLACK_BOT_ICONURL,
            text=message
        )

    def post_image_to_channel(self, channel_name: str, image_object: BinaryIO, title: str = 'Test Upload') -> None:
        """
        Post an Image to a given channel.
        """
        channel_id = self._get_channel_id(channel_name)

        self.sc.api_call(
            "files.upload",
            channels=channel_id,
            file=image_object.read(),
            title=title,
        )
