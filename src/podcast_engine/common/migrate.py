import argparse
from pathlib import Path

from sqlalchemy import Engine, text

from podcast_engine.common.config import get_settings
from podcast_engine.common.db import get_engine
from podcast_engine.common.logging import configure_logging, get_logger

_LOCK_ID = 727_164_000


def apply_migrations(engine: Engine, directory: Path) -> list[str]:
    """Apply every not-yet-applied ``*.sql`` migration, in name order.

    Postgres runs db/init only when its volume is first created, so schema changes after that live
    in migrations. Each file is applied once and recorded in ``schema_migrations``, all in one
    transaction. A Postgres advisory lock (one fixed id shared by every migrator) makes concurrent
    starts safe.

    Args:
        engine: The database to migrate.
        directory: The folder of ``*.sql`` files.

    Returns:
        The names of the files applied now; empty when the database was up to date.

    Raises:
        FileNotFoundError: The folder holds no ``*.sql`` files.
    """
    files = sorted(directory.glob("*.sql"))
    if not files:
        raise FileNotFoundError(f"no migrations in {directory}")
    applied_now: list[str] = []
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": _LOCK_ID})
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
            )
        )
        done = {row[0] for row in connection.execute(text("SELECT name FROM schema_migrations"))}
        for path in files:
            if path.name in done:
                continue
            connection.exec_driver_sql(path.read_text(encoding="utf-8"))
            connection.execute(
                text("INSERT INTO schema_migrations (name) VALUES (:name)"), {"name": path.name}
            )
            applied_now.append(path.name)
    return applied_now


def main(argv: list[str] | None = None) -> None:
    """Migrate the configured database: ``python -m podcast_engine.common.migrate``.

    Docker Compose runs this as the one-shot ``db-migrate`` service.

    Args:
        argv: Command-line arguments (``--dir``); the process's own when None.
    """
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Apply db/migrations/*.sql in order, once each.")
    parser.add_argument("--dir", type=Path, default=settings.migrations_dir)
    args = parser.parse_args(argv)
    configure_logging(settings.log_level)
    applied = apply_migrations(get_engine(), args.dir)
    get_logger("migrate").info("migrations_applied", applied=applied or "none, already up to date")


if __name__ == "__main__":
    main()
