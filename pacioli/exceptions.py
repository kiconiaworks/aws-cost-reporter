class SlackError(Exception):
    """General Slack Error."""
    pass


class SlackChannelError(Exception):
    """Raise when Slack Channel not found."""
    pass
