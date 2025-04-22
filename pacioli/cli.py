"""CLI for testing manually."""

import logging

from .handlers.events import post_status

logger = logging.getLogger(__name__)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--post-to-slack",
        dest="post_to_slack",
        action="store_true",
        default=False,
        help="If given, results will be posted to slack.",
    )

    args = parser.parse_args()
    event = {"post_to_slack": args.post_to_slack}
    post_status(event, None)
