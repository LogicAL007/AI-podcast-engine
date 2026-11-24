from typing import Any, Protocol
from uuid import UUID

import boto3

from podcast_engine.common.config import Settings


class ObjectStore(Protocol):
    """The storage operations stages depend on, so tests can swap in a fake."""

    def put(self, key: str, data: bytes, content_type: str) -> None:
        """Store an object, replacing any with the same key.

        Args:
            key: The object's key.
            data: Its bytes.
            content_type: Its media type.
        """
        ...

    def get(self, key: str) -> bytes:
        """Read an object.

        Args:
            key: The object's key.

        Returns:
            Its bytes.
        """
        ...

    def exists(self, key: str) -> bool:
        """Check whether an object exists.

        Args:
            key: The object's key.

        Returns:
            True when the object exists.
        """
        ...

    def delete(self, key: str) -> None:
        """Remove an object; deleting a missing key is not an error.

        Args:
            key: The object's key.
        """
        ...


class S3ObjectStore:
    """Object storage on any S3-compatible service (RustFS locally in compose)."""

    def __init__(self, settings: Settings) -> None:
        """Create a client for the configured bucket.

        Args:
            settings: The endpoint, credentials, region and bucket name.
        """
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
        """Create the bucket if it is missing.

        Outside us-east-1 the bucket is created in the configured region; S3 rejects an explicit
        location constraint for us-east-1 itself.

        Returns:
            True if the bucket was created, False if it already existed.
        """
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except self._client.exceptions.ClientError:
            options: dict[str, Any] = {"Bucket": self._bucket}
            if self._region != "us-east-1":
                options["CreateBucketConfiguration"] = {"LocationConstraint": self._region}
            self._client.create_bucket(**options)
            return True
        return False

    def put(self, key: str, data: bytes, content_type: str) -> None:
        """Store an object, replacing any with the same key.

        Args:
            key: The object's key.
            data: Its bytes.
            content_type: Its media type.
        """
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        """Read an object.

        Args:
            key: The object's key.

        Returns:
            Its bytes.
        """
        body: bytes = self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        return body

    def exists(self, key: str) -> bool:
        """Check whether an object exists.

        Args:
            key: The object's key.

        Returns:
            True when the object exists.
        """
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
        except self._client.exceptions.ClientError:
            return False
        return True

    def delete(self, key: str) -> None:
        """Remove an object; S3 ignores a missing key.

        Args:
            key: The object's key.
        """
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def check(self) -> None:
        """Raise if the bucket cannot be reached (the API's readiness check)."""
        self._client.head_bucket(Bucket=self._bucket)


def feed_key(show_id: UUID) -> str:
    """Return the object key of a show's RSS feed.

    The publish stage writes it; the API serves it.

    Args:
        show_id: The show.

    Returns:
        The feed's key in object storage.
    """
    return f"feeds/{show_id}.xml"
