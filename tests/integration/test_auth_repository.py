"""The Postgres auth repository against a real database, through the real AuthService."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from podcast_engine.api.errors import ConflictError, InvalidInputError, UnauthenticatedError
from podcast_engine.api.repositories.auth_repository import PostgresAuthRepository
from podcast_engine.api.services.auth_service import AuthService
from podcast_engine.common.mailer import Email
from tests.integration.test_pipeline import engine as engine  # the shared fixture

pytestmark = pytest.mark.integration
PASSWORD = "an integration test passphrase"


@pytest.fixture
def service(engine: Engine) -> Iterator[tuple[AuthService, list[datetime]]]:
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users"))  # the throwaway test database only
    clock = [datetime.now(UTC)]
    with Session(engine) as session:
        yield (
            AuthService(
                PostgresAuthRepository(session), token_key=b"k", token_days=180,
                now=lambda: clock[0],
            ),
            clock,
        )  # fmt: skip
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users"))


def test_accounts_tokens_and_keys_in_sql(service: tuple[AuthService, list[datetime]]) -> None:
    auth, clock = service
    admin = auth.register("Ada@Example.org", PASSWORD, "creator", by=None)
    assert admin.role == "admin"
    with pytest.raises(ConflictError):
        auth.register("ada@example.org", PASSWORD, "creator", by=auth.authenticate(
            auth.login("ada@example.org", PASSWORD).access_token
        ))  # fmt: skip

    session = auth.login("ADA@example.org", PASSWORD)
    me = auth.authenticate(session.access_token)
    assert me.email == "Ada@Example.org"
    key = auth.create_api_key(me, "nightly job")
    assert auth.authenticate(key.key).token_kind == "api_key"
    keys = auth.list_api_keys(me, limit=10, offset=0)
    assert keys.total == 1
    assert keys.items[0].last_used_at is not None
    assert auth.list_users(me, limit=10, offset=0).total == 1

    auth.revoke_api_key(me, key.token_id)
    with pytest.raises(UnauthenticatedError):
        auth.authenticate(key.key)
    clock[0] += timedelta(days=180)
    with pytest.raises(UnauthenticatedError):
        auth.authenticate(session.access_token)


def token_of(email: Email) -> str:
    return email.body.split("#token=")[1].split()[0]


def test_password_reset_and_revocation_in_sql(service: tuple[AuthService, list[datetime]]) -> None:
    auth, clock = service
    auth.register("grace@example.org", PASSWORD, "creator", by=None)
    session = auth.login("grace@example.org", PASSWORD).access_token
    key = auth.create_api_key(auth.authenticate(session), "job").key

    first = auth.request_reset("grace@example.org")
    second = auth.request_reset("grace@example.org")
    assert first is not None
    assert second is not None
    with pytest.raises(InvalidInputError):  # only the newest link works
        auth.confirm_reset(token_of(first), "a completely new passphrase")
    auth.confirm_reset(token_of(second), "a completely new passphrase")
    for old in (session, key):  # every sign-in ended
        with pytest.raises(UnauthenticatedError):
            auth.authenticate(old)
    with pytest.raises(InvalidInputError):  # used once
        auth.confirm_reset(token_of(second), "yet another passphrase here")
    assert auth.request_reset("nobody@example.org") is None

    now = auth.login("grace@example.org", "a completely new passphrase").access_token
    other = auth.login("grace@example.org", "a completely new passphrase").access_token
    auth.change_password(auth.authenticate(now), "a completely new passphrase", PASSWORD)
    auth.authenticate(now)  # this sign-in kept
    with pytest.raises(UnauthenticatedError):
        auth.authenticate(other)
    assert clock  # the shared clock fixture


def test_account_management_and_security_log_in_sql(engine: Engine) -> None:
    from podcast_engine.api.models.shows_model import ShowCreate
    from podcast_engine.api.repositories.security_events_repository import (
        PostgresSecurityEventRepository,
    )
    from podcast_engine.api.repositories.shows_repository import PostgresShowRepository

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users"))
        connection.execute(text("DELETE FROM security_events"))
    try:
        with Session(engine) as session:
            shows = PostgresShowRepository(session)
            accounts = PostgresAuthRepository(session)
            auth = AuthService(
                accounts, token_key=b"k", token_days=180,
                events=PostgresSecurityEventRepository(session),
                purge_files=lambda owner: len(shows.stored_files(owner_id=owner)),
            )  # fmt: skip
            auth.register("root@example.org", PASSWORD, "creator", by=None, address="10.0.0.1")
            admin = auth.authenticate(auth.login("root@example.org", PASSWORD).access_token)
            other = auth.login("root@example.org", PASSWORD)
            sessions = auth.list_sessions(admin, limit=10, offset=0)
            assert sessions.total == 2
            assert sum(s.current for s in sessions.items) == 1
            auth.revoke_session(admin, other.token_id)
            assert auth.list_sessions(admin, limit=10, offset=0).total == 1

            cleo = auth.register("cleo@example.org", PASSWORD, "creator", by=admin)
            show = shows.add(
                ShowCreate(topic="tides", sources=["https://example.org/a"]), cleo.user_id
            )
            assert shows.stored_files(show_id=show.show_id) == [f"feeds/{show.show_id}.xml"]
            assert auth.update_user(admin, cleo.user_id, role=None, disabled=True).disabled
            with pytest.raises(ConflictError):
                auth.change_email(admin, PASSWORD, "cleo@example.org")
            auth.change_email(admin, PASSWORD, "boss@example.org")
            assert auth.authenticate(auth.login("boss@example.org", PASSWORD).access_token)

            assert auth.delete_user(admin, cleo.user_id) == 1  # the feed key
            assert shows.get(show.show_id, cleo.user_id) is None
            with pytest.raises(ConflictError):  # never on yourself
                auth.update_user(admin, admin.user_id, role="creator", disabled=None)

            log = auth.list_events(admin, user_id=None, event=None, limit=50, offset=0)
            names = [row.event for row in log.items]
            assert names[0] == "user_deleted"
            assert names[-1] == "user_registered"
            assert log.items[-1].address == "10.0.0.1"
            deleted = auth.list_events(admin, user_id=None, event="user_registered", limit=5,
                                       offset=0)  # fmt: skip
            assert [row.user_id for row in deleted.items].count(None) == 1  # cleo's, unlinked

            auth.delete_account(admin, PASSWORD)  # the last admin, but alone now: allowed
            assert accounts.count_users() == 0
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM users"))
            connection.execute(text("DELETE FROM security_events"))


def test_the_chosen_bot_is_stored_and_returned_with_the_user(
    service: tuple[AuthService, list[datetime]],
) -> None:
    from podcast_engine.api.models.auth_model import Avatar

    auth, _ = service
    auth.register("ada@example.org", PASSWORD, "creator", by=None)
    token = auth.login("ada@example.org", PASSWORD).access_token
    me = auth.authenticate(token)
    assert me.avatar is None
    auth.set_avatar(me, Avatar(character="rex", name="Rex", color="sky", accessory="headphones"))
    again = auth.authenticate(token)
    assert again.avatar == Avatar(character="rex", name="Rex", color="sky", accessory="headphones")
