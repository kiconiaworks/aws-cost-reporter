"""Define Clients, Resources and utilities for interfacing with AWS."""

from urllib.parse import urlparse

import boto3

from . import settings

S3_CLIENT = boto3.client("s3", endpoint_url=settings.AWS_SERVICE_ENDPOINTS["s3"])
S3_RESOURCE = boto3.resource("s3", endpoint_url=settings.AWS_SERVICE_ENDPOINTS["s3"])

CE_CLIENT = boto3.client("ce")


def parse_s3_uri(uri: str) -> tuple[str, str]:
    """Parse s3 uri (s3://bucket/key) to (bucket, key)."""
    result = urlparse(uri)
    bucket = result.netloc
    key = result.path[1:]  # removes leading slash
    return bucket, key
