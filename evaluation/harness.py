"""Shared plumbing for the evaluation scripts: run the real pipeline in-process, keep every output.

The benchmarks use the same stage code as the workers (``podcast_engine.pipeline.run_inline``), so
what is measured is what ships. Audio, notes and feeds go to a folder instead of S3, so a run can
be listened to and archived with its results.
"""

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, create_engine, text

from podcast_engine.common.config import Settings
from podcast_engine.common.context import PipelineContext
from podcast_engine.common.migrate import apply_migrations
from podcast_engine.common.repository import PipelineRepository

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluation" / "results"
# A throwaway pgvector database: `make bench-db` starts one on this port with db/init applied.
DEFAULT_DATABASE_URL = "postgresql+psycopg://podcast:bench@127.0.0.1:55433/podcast"


class DirectoryStore:
    """Object storage in a local folder, keyed like S3 (``episodes/<id>.wav`` and so on)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.writes = 0

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError(f"key escapes the store: {key}")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:  # noqa: ARG002
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.writes += 1

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()


def engine_from_env() -> Engine:
    engine = create_engine(os.environ.get("BENCH_DATABASE_URL", DEFAULT_DATABASE_URL))
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    apply_migrations(engine, ROOT / "db" / "migrations")
    return engine


def bench_settings(engine: Engine, **overrides: Any) -> Settings:
    """Settings for an in-process run: repository folders, offline unless overridden."""
    values: dict[str, Any] = {
        "database_url": str(engine.url),
        "llm_enabled": False,
        "tts_backend": "placeholder",
        "embedding_model": "hashing",
        "config_dir": ROOT / "config",
        "prompts_dir": ROOT / "prompts",
        "assets_dir": ROOT / "assets",
    }
    values.update(overrides)
    secret = ROOT / "secrets" / "llm_api_key.txt"
    if values["llm_enabled"] and "llm_api_key_file" not in values and secret.exists():
        values["llm_api_key_file"] = secret  # read from the file; never printed or stored
    return Settings(_env_file=None, **values)


@dataclass
class Bench:
    engine: Engine
    settings: Settings
    store: DirectoryStore
    fetch: Callable[[str], str] | None = None

    def context(self) -> PipelineContext:
        return PipelineContext(
            settings=self.settings,
            repo=PipelineRepository(self.engine),
            store=self.store,
            fetch=self.fetch,
        )

    def create_show(self, **fields: Any) -> UUID:
        columns = {
            "topic": fields["topic"],
            "tone": fields.get("tone", "casual"),
            "target_minutes": fields.get("target_minutes", 7),
            "host_count": fields.get("host_count", 2),
            "expertise": fields.get("expertise", "beginner"),
            "sources": json.dumps(fields["sources"]),
            "topic_keywords": fields.get("topic_keywords", ""),
            "attribution": fields.get("attribution", ""),
            "max_segments": fields.get("max_segments", 6),
            "ranking_profile": fields.get("ranking_profile", "explainer"),
        }
        with self.engine.begin() as connection:
            show_id: UUID = connection.execute(
                text(
                    "INSERT INTO shows (topic, tone, target_minutes, host_count, expertise,"
                    " sources, topic_keywords, attribution, max_segments, ranking_profile)"
                    " VALUES (:topic,"
                    " :tone, :target_minutes, :host_count, :expertise, CAST(:sources AS jsonb),"
                    " :topic_keywords, :attribution, :max_segments, :ranking_profile)"
                    " RETURNING show_id"
                ),
                columns,
            ).scalar_one()
        return show_id


def run_folder(name: str) -> Path:
    folder = RESULTS / name / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def caching_fetch(cache_dir: Path) -> Callable[[str], str]:
    """Fetch each page once and keep the HTML, so all conditions and reruns sees the same text."""
    from podcast_engine.stages.ingest.extract import fetch_html

    cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch(url: str) -> str:
        import hashlib

        path = cache_dir / (hashlib.sha256(url.encode()).hexdigest()[:16] + ".html")
        if not path.exists():
            path.write_text(fetch_html(url), encoding="utf-8")
        return path.read_text(encoding="utf-8")

    return fetch
