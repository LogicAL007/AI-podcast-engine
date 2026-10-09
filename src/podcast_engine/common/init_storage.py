"""One-shot job that creates the episode bucket: ``python -m podcast_engine.common.init_storage``.

Safe to run on every start. Compose runs it as ``s3-init`` and makes every other service wait
for it to finish.
"""

from podcast_engine.common.config import get_settings
from podcast_engine.common.logging import configure_logging, get_logger
from podcast_engine.common.storage import S3ObjectStore


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    created = S3ObjectStore(settings).ensure_bucket()
    get_logger("init_storage").info("bucket_ready", bucket=settings.s3_bucket, created=created)


if __name__ == "__main__":
    main()
