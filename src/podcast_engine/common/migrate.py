"""Apply db/migrations/*.sql in order, once each: ``python -m podcast_engine.common.migrate``.

Postgres runs db/init only when its volume is first created, so schema changes after that live here.
Each file is applied in its own transaction and recorded in ``schema_migrations``. An advisory lock
makes concurrent starts safe. Compose runs this as the one-shot ``db-migrate`` service.
"""

import argparse
from pathlib import Path

from sqlalchemy import Engine, text

from podcast_engine.common.config import get_settings
from podcast_engine.common.db import get_engine
from podcast_engine.common.logging import configure_logging, get_logger

_LOCK_ID = 727_164_000  # any constant; shared by every migrator


def apply_migrations(engine: Engine, directory: Path) -> list[str]:
    """Apply every not-yet-applied ``*.sql`` file in name order and return the names applied."""
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
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=settings.migrations_dir)
    args = parser.parse_args(argv)
    configure_logging(settings.log_level)
    applied = apply_migrations(get_engine(), args.dir)
    get_logger("migrate").info("migrations_applied", applied=applied or "none, already up to date")


if __name__ == "__main__":
    main()
