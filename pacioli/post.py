import os
from slackclient import SlackClient

COST_CHANNEL_NAME = os.getenv('PACIOLI_SLACK_CHANNEL', 'cost_management')
SLACK_TOKEN = os.getenv('SLACK_API_TOKEN', None)
DEFAULT_TEST_MESSAGE = ":fire: :heavy_dollar_sign::heavy_dollar_sign: :fire: Accounting Rules :fire: :heavy_dollar_sign::heavy_dollar_sign: :fire:"


def post_to_channel(channel_name=COST_CHANNEL_NAME, message=DEFAULT_TEST_MESSAGE):
    sc = SlackClient(SLACK_TOKEN)

    # get channel id for channel name
    channel_id = None
    channel_query_response = sc.api_call('channels.list', exclude_archived=True)
    for channel_info in channel_query_response['channels']:
        if channel_info['name'] == channel_name:
            channel_id = channel_info['id']
            break

    sc.api_call(
        "chat.postMessage",
        channel=channel_id,
        username='pacioli',
        icon_url='http://images.sciencelibrary.info/history/topic51/52/pacioli_luca_portrait.jpg',
        text=message
    )


    # with open('thinking_very_much.png') as file_content:
    #     sc.api_call(
    #         "files.upload",
    #         channels="C3UKJTQAC",
    #         file=file_content,
    #         title="Test upload"
    #     )


if __name__ == '__main__':
    post_to_channel()
