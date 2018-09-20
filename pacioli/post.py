import os
from slackclient import SlackClient

COST_CHANNEL_NAME = os.getenv('PACIOLI_SLACK_CHANNEL', 'cost_management')
SLACK_TOKEN = os.getenv('SLACK_API_TOKEN', None)
SLACK_BOT_NAME = os.getenv('SLACK_BOT_NAME', 'pacioli')
SLACK_BOT_ICONURL = os.getenv('SLACK_BOT_ICONURL', 'http://images.sciencelibrary.info/history/topic51/52/pacioli_luca_portrait.jpg')
DEFAULT_TEST_MESSAGE = ":fire: :heavy_dollar_sign::heavy_dollar_sign: :fire: Accounting Rules :fire: :heavy_dollar_sign::heavy_dollar_sign: :fire:"


class SlackError(Exception):
    pass

class SlackChannelError(Exception):
    pass


if not SLACK_TOKEN:
    raise SlackError('"SLACK_API_TOKEN" environment variable not set!')


class SlackPostManager:

    def __init__(self, token=SLACK_TOKEN):
        self.sc = SlackClient(token)

    def _get_channel_id(self, channel_name):
        # get channel id for channel name
        channel_id = None
        channel_query_response = self.sc.api_call('channels.list',
                                                  exclude_archived=True)
        for channel_info in channel_query_response['channels']:
            if channel_info['name'] == channel_name:
                channel_id = channel_info['id']
                break
        if not channel_id:
            raise SlackChannelError(f'"{channel_name}" not found!')

        return channel_id

    def post_message_to_channel(self, channel_name=COST_CHANNEL_NAME, message=DEFAULT_TEST_MESSAGE):
        channel_id = self._get_channel_id(channel_name)
        self.sc.api_call(
            "chat.postMessage",
            channel=channel_id,
            username=SLACK_BOT_NAME,
            icon_url=SLACK_BOT_ICONURL,
            text=message
        )

    def post_image_to_channel(self, channel_name, filepath, title='Test Upload'):
        channel_id = self._get_channel_id(channel_name)
        with open(filepath, 'rb') as file_content:
            self.sc.api_call(
                "files.upload",
                channels=channel_id,
                file=file_content,
                title=title,
            )


if __name__ == '__main__':
    slack = SlackPostManager()
    slack.post_message_to_channel()
