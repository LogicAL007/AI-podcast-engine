"""Registered voices in Postgres: storing, ownership, withdrawal from shows, and pipeline reads."""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from podcast_engine.api.models.shows_model import ShowCreate
from podcast_engine.api.repositories.auth_repository import PostgresAuthRepository
from podcast_engine.api.repositories.shows_repository import PostgresShowRepository
from podcast_engine.api.repositories.voices_repository import PostgresVoiceRepository
from podcast_engine.common.repository import PipelineRepository
from tests.integration.test_pipeline import engine as engine  # the shared fixture

pytestmark = pytest.mark.integration


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users"))  # the throwaway test database only
    with Session(engine) as session:
        yield session
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users"))


def test_voices_in_sql(session: Session, engine: Engine) -> None:
    owner = PostgresAuthRepository(session).add_user("ada@example.org", "x", "admin").user_id
    voices = PostgresVoiceRepository(session)
    voice_id = uuid4()
    voice = voices.add(
        owner,
        {
            "voice_id": voice_id,
            "name": "My voice",
            "speaker": "Ada",
            "license": "Own recording",
            "source": "recorded",
            "consent": {"signed_by": "Ada", "relationship": "self", "version": "v",
                        "statement": "s", "permission_record": "",
                        "agreed_at": "2026-10-25T10:00:00+00:00"},
            "object_key": f"voices/{owner}/{voice_id}.wav",
            "size_bytes": 1000,
            "duration_seconds": 8.0,
            "sha256": "abc",
        },
    )  # fmt: skip
    assert voice.consent.signed_by == "Ada"
    assert voices.owned({voice_id, uuid4()}, owner) == {voice_id}
    assert voices.owned({voice_id}, uuid4()) == set()

    shows = PostgresShowRepository(session)
    show = shows.add(ShowCreate(topic="Tides", host_voices={"Alex": voice_id}), owner)
    assert show.host_voices == {"Alex": voice_id}

    pipeline = PipelineRepository(engine)
    assert pipeline.get_show(show.show_id).host_voices == {"Alex": str(voice_id)}
    found = pipeline.get_voices([str(voice_id), str(uuid4())])
    assert list(found) == [str(voice_id)]
    assert found[str(voice_id)].consent["relationship"] == "self"

    assert voices.delete(voice_id, owner)
    assert shows.get(show.show_id, owner).host_voices == {}  # type: ignore[union-attr]
    assert voices.object_keys(owner) == []
