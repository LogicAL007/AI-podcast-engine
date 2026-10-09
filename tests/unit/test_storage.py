from typing import Any

from podcast_engine.common.config import Settings
from podcast_engine.common.storage import S3ObjectStore


class _FakeClientError(Exception):
    pass


class _FakeS3Client:
    """Just enough of the boto3 client to drive ``ensure_bucket``."""

    class exceptions:  # noqa: N801 - mirrors boto3's client.exceptions
        ClientError = _FakeClientError

    def __init__(self, *, bucket_exists: bool) -> None:
        self.bucket_exists = bucket_exists
        self.created: list[dict[str, Any]] = []

    def head_bucket(self, **_: Any) -> None:
        if not self.bucket_exists:
            raise _FakeClientError

    def create_bucket(self, **options: Any) -> None:
        self.created.append(options)


def _store(client: _FakeS3Client, region: str = "us-east-1") -> S3ObjectStore:
    store = S3ObjectStore(Settings(s3_region=region))
    store._client = client
    return store


def test_ensure_bucket_creates_when_missing() -> None:
    client = _FakeS3Client(bucket_exists=False)
    assert _store(client).ensure_bucket() is True
    assert client.created == [{"Bucket": "podcast-episodes"}]


def test_ensure_bucket_is_idempotent() -> None:
    client = _FakeS3Client(bucket_exists=True)
    assert _store(client).ensure_bucket() is False
    assert client.created == []


def test_non_default_region_sets_location_constraint() -> None:
    client = _FakeS3Client(bucket_exists=False)
    _store(client, region="eu-west-1").ensure_bucket()
    assert client.created[0]["CreateBucketConfiguration"] == {"LocationConstraint": "eu-west-1"}
