"""Define exceptions for use in the paciolli package."""


class SlackError(Exception):
    """General Slack Error."""


class SlackChannelError(Exception):
    """Raise when Slack Channel not found."""
