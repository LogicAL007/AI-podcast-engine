"""Runs the Postgres repositories against a real database.

Needs the schema from db/init applied. Start it with ``docker compose up -d postgres`` and run:
``DATABASE_URL=postgresql+psycopg://... pytest -m integration``. Skipped when unreachable.
"""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from podcast_engine.api.models.shows_model import ShowCreate
from podcast_engine.api.repositories.episodes_repository import PostgresEpisodeRepository
from podcast_engine.api.repositories.shows_repository import PostgresShowRepository
from podcast_engine.common.db import get_engine
from podcast_engine.common.models import EpisodeStatus

pytestmark = pytest.mark.integration


@pytest.fixture
def session() -> Iterator[Session]:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1 FROM shows LIMIT 1"))
    except OperationalError:
        pytest.skip("Postgres not reachable")
    with Session(get_engine()) as db:
        yield db


def _owner(session: Session) -> UUID:
    user_id: UUID = session.execute(
        text("INSERT INTO users (email, password_hash) VALUES (:email, 'x') RETURNING user_id"),
        {"email": f"repo-{uuid4()}@example.invalid"},
    ).scalar_one()
    session.commit()
    return user_id


def test_show_crud_round_trip(session: Session) -> None:
    shows = PostgresShowRepository(session)
    owner = _owner(session)
    created = shows.add(
        ShowCreate(topic="Integration topic", sources=["https://example.org/a"]), owner
    )
    try:
        assert shows.get(created.show_id, owner) == created
        assert shows.get(created.show_id, uuid4()) is None  # someone else's: not there
        updated = shows.update(
            created.show_id, owner, {"host_count": 3, "sources": ["https://x.org/b"]}
        )
        assert updated is not None
        assert updated.host_count == 3
        assert updated.sources == ["https://x.org/b"]
        listed = shows.list_page(owner, limit=100, offset=0).items
        assert created.show_id in [s.show_id for s in listed]
        assert shows.list_page(uuid4(), limit=100, offset=0).total == 0
    finally:
        assert not shows.delete(created.show_id, uuid4())  # not someone else's to delete
        assert shows.delete(created.show_id, owner)
    assert shows.get(created.show_id, owner) is None
    assert shows.update(uuid4(), owner, {"topic": "nope"}) is None


def test_episode_lifecycle_and_cascade(session: Session) -> None:
    shows = PostgresShowRepository(session)
    episodes = PostgresEpisodeRepository(session)
    owner = _owner(session)
    show = shows.add(ShowCreate(topic="Episode owner"), owner)
    episode = episodes.add(show.show_id)
    assert episode.status is EpisodeStatus.QUEUED

    episodes.set_status(episode.episode_id, EpisodeStatus.FAILED)
    fetched = episodes.get(episode.episode_id, owner)
    assert fetched is not None
    assert fetched.status is EpisodeStatus.FAILED
    listed = episodes.list_page(owner, show_id=show.show_id, status=None, limit=10, offset=0)
    assert [e.episode_id for e in listed.items] == [episode.episode_id]
    assert listed.total == 1
    stranger = _owner(session)  # another account: the episode is not theirs, so not there
    assert episodes.get(episode.episode_id, stranger) is None
    assert episodes.list_page(stranger, show_id=None, status=None, limit=10, offset=0).total == 0
    assert (
        episodes.list_page(stranger, show_id=show.show_id, status=None, limit=10, offset=0).items
        == []
    )

    shows.delete(show.show_id, owner)
    assert episodes.get(episode.episode_id, owner) is None
