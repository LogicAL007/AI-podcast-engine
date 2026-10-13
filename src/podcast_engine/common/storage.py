"""S3-compatible object storage (RustFS locally in compose, any S3 service in production)."""

from typing import Any, Protocol
from uuid import UUID

import boto3

from podcast_engine.common.config import Settings


class ObjectStore(Protocol):
    """The storage operations stages depend on, so tests can swap in a fake."""

    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None:
        """Remove the object; deleting a missing key is not an error."""
        ...


class S3ObjectStore:
    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.s3_bucket
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
        )
        self._region = settings.s3_region

    def ensure_bucket(self) -> bool:
        """Create the bucket if it is missing. Returns True if it was created."""
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except self._client.exceptions.ClientError:
            options: dict[str, Any] = {"Bucket": self._bucket}
            if self._region != "us-east-1":  # S3 rejects an explicit constraint for us-east-1
                options["CreateBucketConfiguration"] = {"LocationConstraint": self._region}
            self._client.create_bucket(**options)
            return True
        return False

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        body: bytes = self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        return body

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
        except self._client.exceptions.ClientError:
            return False
        return True

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)  # S3 ignores a missing key

    def check(self) -> None:
        """Raise if the bucket cannot be reached (the API's readiness check)."""
        self._client.head_bucket(Bucket=self._bucket)


def feed_key(show_id: UUID) -> str:
    """Object key of a show's RSS feed. The publish stage writes it; the API serves it."""
    return f"feeds/{show_id}.xml"
