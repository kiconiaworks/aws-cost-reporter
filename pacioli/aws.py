"""
Define Clients, Resources and utilities for interfacing with AWS.
"""
from typing import Tuple
from urllib.parse import urlparse

import boto3

from . import settings

S3_CLIENT = boto3.client("s3", endpoint_url=settings.AWS_SERVICE_ENDPOINTS["s3"])
S3_RESOURCE = boto3.resource("s3", endpoint_url=settings.AWS_SERVICE_ENDPOINTS["s3"])


def parse_s3_uri(uri: str) -> Tuple[str, str]:
    """
    Parse s3 uri (s3://bucket/key) to (bucket, key).
    """
    result = urlparse(uri)
    bucket = result.netloc
    key = result.path[1:]  # removes leading slash
    return bucket, key
