"""In-memory stand-ins for the repositories and object store, used by API tests."""

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from podcast_engine.api.models.episodes_model import (
    ClaimDetail,
    EpisodeFiles,
    EpisodeRead,
    EpisodeScript,
    StageRunRead,
)
from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.models.shows_model import ShowCreate, ShowRead
from podcast_engine.api.models.sources_model import SourceRead
from podcast_engine.api.models.uploads_model import UploadRead
from podcast_engine.common.models import EpisodeStatus


def page[T](items: list[T], limit: int, offset: int) -> Paged[T]:
    return Paged(items[offset : offset + limit], len(items))


class FakeShowRepository:
    """Shows with their owners; like the SQL, another owner's show is simply not there."""

    def __init__(self) -> None:
        self.rows: dict[UUID, ShowRead] = {}
        self.owners: dict[UUID, UUID | None] = {}

    def add(self, data: ShowCreate, owner_id: UUID) -> ShowRead:
        show = ShowRead(
            show_id=uuid4(),
            created_at=datetime.now(UTC),
            **{**data.model_dump(), "sources": [str(url) for url in data.sources]},
        )
        self.rows[show.show_id] = show
        self.owners[show.show_id] = owner_id
        return show

    def owned(self, show_id: UUID, owner_id: UUID) -> bool:
        return show_id in self.rows and self.owners.get(show_id) == owner_id

    def get(self, show_id: UUID, owner_id: UUID) -> ShowRead | None:
        return self.rows[show_id] if self.owned(show_id, owner_id) else None

    def list_page(self, owner_id: UUID, *, limit: int, offset: int) -> Paged[ShowRead]:
        shows = sorted(
            (s for s in self.rows.values() if self.owners.get(s.show_id) == owner_id),
            key=lambda show: show.created_at,
            reverse=True,
        )
        return page(shows, limit, offset)

    def update(self, show_id: UUID, owner_id: UUID, changes: Mapping[str, Any]) -> ShowRead | None:
        if not self.owned(show_id, owner_id):
            return None
        updated = self.rows[show_id].model_copy(update=dict(changes))
        self.rows[show_id] = updated
        return updated

    def delete(self, show_id: UUID, owner_id: UUID) -> bool:
        if not self.owned(show_id, owner_id):
            return False
        del self.rows[show_id]
        return True

    def stored_files(
        self, *, owner_id: UUID | None = None, show_id: UUID | None = None
    ) -> list[str]:
        """The feeds only: the fake episodes and uploads keep their own keys."""
        return [
            f"feeds/{sid}.xml"
            for sid in self.rows
            if sid == show_id or (owner_id is not None and self.owners.get(sid) == owner_id)
        ]

    def drop_owner(self, owner_id: UUID) -> None:
        """What deleting the owning user cascades to."""
        for sid in [sid for sid, owner in self.owners.items() if owner == owner_id]:
            self.rows.pop(sid, None)
            self.owners.pop(sid, None)

    def claim_unowned(self, owner_id: UUID) -> int:
        unowned = [show_id for show_id, owner in self.owners.items() if owner is None]
        for show_id in unowned:
            self.owners[show_id] = owner_id
        return len(unowned)


class FakeEpisodeRepository:
    """Episodes are someone's through their show, as in the SQL."""

    def __init__(self, shows: FakeShowRepository) -> None:
        self.shows = shows
        self.rows: dict[UUID, EpisodeRead] = {}
        self.scripts: dict[UUID, EpisodeScript] = {}
        self.raw_scripts: dict[UUID, dict[str, Any]] = {}
        self.positions: dict[UUID, list[int]] = {}
        self.show_chunks: dict[UUID, set[UUID]] = {}
        self.runs: dict[UUID, list[StageRunRead]] = {}
        self.claims: dict[UUID, list[ClaimDetail]] = {}
        self.files: dict[UUID, EpisodeFiles] = {}

    def add(self, show_id: UUID) -> EpisodeRead:
        episode = EpisodeRead(
            episode_id=uuid4(),
            show_id=show_id,
            status=EpisodeStatus.QUEUED,
            rewrite_count=0,
            created_at=datetime.now(UTC),
            published_at=None,
        )
        self.rows[episode.episode_id] = episode
        return episode

    def get(self, episode_id: UUID, owner_id: UUID) -> EpisodeRead | None:
        episode = self.rows.get(episode_id)
        if episode is None or not self.shows.owned(episode.show_id, owner_id):
            return None
        return episode

    def list_page(
        self,
        owner_id: UUID,
        *,
        show_id: UUID | None,
        status: EpisodeStatus | None,
        limit: int,
        offset: int,
    ) -> Paged[EpisodeRead]:
        rows = [
            row
            for row in sorted(self.rows.values(), key=lambda e: e.created_at, reverse=True)
            if self.shows.owned(row.show_id, owner_id)
            and (show_id is None or row.show_id == show_id)
            and (status is None or row.status is status)
        ]
        return page(rows, limit, offset)

    def set_status(self, episode_id: UUID, status: EpisodeStatus) -> None:
        self.update(episode_id, status=status)

    def update(self, episode_id: UUID, **fields: Any) -> None:
        self.rows[episode_id] = self.rows[episode_id].model_copy(update=fields)

    def delete(self, episode_id: UUID) -> bool:
        return self.rows.pop(episode_id, None) is not None

    def get_script(self, episode_id: UUID) -> EpisodeScript | None:
        if episode_id not in self.rows:
            return None
        return self.scripts.get(episode_id, EpisodeScript(episode_id=episode_id, segments=[]))

    def get_raw_script(self, episode_id: UUID) -> dict[str, Any] | None:
        if episode_id not in self.rows:
            return None
        return self.raw_scripts.get(episode_id, {})

    def save_script(self, episode_id: UUID, script: dict[str, Any]) -> None:
        self.raw_scripts[episode_id] = script

    def segment_positions(self, episode_id: UUID) -> list[int]:
        return self.positions.get(episode_id, [])

    def chunks_in_show(self, show_id: UUID, chunk_ids: Iterable[UUID]) -> set[UUID]:
        return set(chunk_ids) & self.show_chunks.get(show_id, set())

    def list_runs(self, episode_id: UUID, *, limit: int, offset: int) -> Paged[StageRunRead]:
        return page(self.runs.get(episode_id, []), limit, offset)

    def list_claims(
        self,
        episode_id: UUID,
        *,
        supported: bool | None,
        segment: int | None,
        limit: int,
        offset: int,
    ) -> Paged[ClaimDetail]:
        rows = [
            c
            for c in self.claims.get(episode_id, [])
            if (supported is None or c.supported is supported)
            and (segment is None or c.segment == segment)
        ]
        return page(rows, limit, offset)

    def get_files(self, episode_id: UUID) -> EpisodeFiles | None:
        if episode_id not in self.rows:
            return None
        return self.files.get(episode_id, EpisodeFiles(audio_key=None, notes_key=None))


class FakeSourceRepository:
    def __init__(self) -> None:
        self.rows: dict[UUID, list[SourceRead]] = {}

    def list_page(self, show_id: UUID, *, limit: int, offset: int) -> Paged[SourceRead]:
        return page(self.rows.get(show_id, []), limit, offset)


class FakeUploadRepository:
    def __init__(self) -> None:
        self.rows: dict[UUID, UploadRead] = {}

    def add(self, **fields: Any) -> UploadRead:
        upload = UploadRead(created_at=datetime.now(UTC), **fields)
        self.rows[upload.upload_id] = upload
        return upload

    def get(self, show_id: UUID, upload_id: UUID) -> UploadRead | None:
        upload = self.rows.get(upload_id)
        return upload if upload is not None and upload.show_id == show_id else None

    def list_page(self, show_id: UUID, *, limit: int, offset: int) -> Paged[UploadRead]:
        rows = sorted(
            (u for u in self.rows.values() if u.show_id == show_id),
            key=lambda u: u.created_at,
            reverse=True,
        )
        return page(rows, limit, offset)

    def delete(self, show_id: UUID, upload_id: UUID) -> bool:
        if self.get(show_id, upload_id) is None:
            return False
        del self.rows[upload_id]
        return True


class FakeObjectStore:
    def __init__(self, objects: dict[str, bytes] | None = None) -> None:
        self.objects = objects or {}

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def exists(self, key: str) -> bool:
        return key in self.objects

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


class FakeAuthRepository:
    """Users and tokens in memory, with the same semantics as the Postgres repository."""

    def __init__(self) -> None:
        from podcast_engine.api.models.auth_model import StoredUser

        self.users: dict[UUID, StoredUser] = {}
        self.tokens: dict[UUID, dict[str, Any]] = {}
        self.resets: dict[UUID, dict[str, Any]] = {}
        self.on_delete: list[Any] = []  # like ON DELETE CASCADE: called with the user's id

    def count_users(self) -> int:
        return len(self.users)

    def add_user(self, email: str, password_hash: str, role: Any) -> Any:
        from podcast_engine.api.errors import ConflictError
        from podcast_engine.api.models.auth_model import StoredUser, UserRead

        if self.find_user(email) is not None:
            raise ConflictError(f"an account with the email {email} already exists")
        user = StoredUser(
            user_id=uuid4(), email=email, role=role, disabled=False,
            created_at=datetime.now(UTC), password_hash=password_hash,
        )  # fmt: skip
        self.users[user.user_id] = user
        return UserRead.model_validate(user.model_dump())

    def find_user(self, email: str) -> Any:
        return next((u for u in self.users.values() if u.email.lower() == email.lower()), None)

    def set_password_hash(self, user_id: UUID, password_hash: str) -> None:
        self.users[user_id] = self.users[user_id].model_copy(
            update={"password_hash": password_hash}
        )

    def list_users(self, *, limit: int, offset: int) -> Any:
        from podcast_engine.api.models.auth_model import UserRead

        users = [UserRead.model_validate(u.model_dump()) for u in self.users.values()]
        return page(users, limit, offset)

    def add_token(self, **fields: Any) -> Any:
        from podcast_engine.api.models.auth_model import ApiKeyRead

        token_id = uuid4()
        row = {
            **fields, "token_id": token_id, "created_at": datetime.now(UTC),
            "last_used_at": None, "revoked_at": None,
        }  # fmt: skip
        self.tokens[token_id] = row
        return ApiKeyRead.model_validate(row)

    def find_token(self, token_hash: str) -> Any:
        from podcast_engine.api.models.auth_model import StoredToken

        row = next((t for t in self.tokens.values() if t["token_hash"] == token_hash), None)
        if row is None:
            return None
        user = self.users[row["user_id"]]
        return StoredToken(
            token_id=row["token_id"], user_id=user.user_id, kind=row["kind"],
            expires_at=row["expires_at"], revoked_at=row["revoked_at"],
            last_used_at=row["last_used_at"], email=user.email, role=user.role,
            disabled=user.disabled,
        )  # fmt: skip

    def touch(self, token_id: UUID, when: datetime) -> None:
        self.tokens[token_id]["last_used_at"] = when

    def revoke(self, token_id: UUID, user_id: UUID, when: datetime) -> bool:
        row = self.tokens.get(token_id)
        if row is None or row["user_id"] != user_id or row["revoked_at"] is not None:
            return False
        row["revoked_at"] = when
        return True

    def list_api_keys(self, user_id: UUID, *, limit: int, offset: int) -> Any:
        from podcast_engine.api.models.auth_model import ApiKeyRead

        keys = [
            ApiKeyRead.model_validate(t)
            for t in sorted(self.tokens.values(), key=lambda t: t["created_at"], reverse=True)
            if t["user_id"] == user_id and t["kind"] == "api_key"
        ]
        return page(keys, limit, offset)

    # ---- password resets and bulk revocation ----------------------------------------------
    def get_user(self, user_id: UUID) -> Any:
        return self.users.get(user_id)

    def revoke_all(self, user_id: UUID, when: datetime, *, keep: UUID | None = None) -> int:
        count = 0
        for token_id, row in self.tokens.items():
            if row["user_id"] == user_id and row["revoked_at"] is None and token_id != keep:
                row["revoked_at"] = when
                count += 1
        return count

    def session_ids(self, user_id: UUID) -> list[UUID]:
        return [
            token_id
            for token_id, row in self.tokens.items()
            if row["user_id"] == user_id and row["kind"] == "session" and row["revoked_at"] is None
        ]

    def add_reset(self, user_id: UUID, token_hash: str, expires_at: datetime) -> None:
        reset_id = uuid4()
        self.resets[reset_id] = {"reset_id": reset_id, "user_id": user_id,
                                    "token_hash": token_hash, "expires_at": expires_at,
                                    "used_at": None}  # fmt: skip

    def find_reset(self, token_hash: str) -> Any:
        from podcast_engine.api.models.auth_model import StoredReset

        row = next((r for r in self.resets.values() if r["token_hash"] == token_hash), None)
        if row is None:
            return None
        user = self.users[row["user_id"]]
        return StoredReset(**{k: v for k, v in row.items() if k != "token_hash"},
                           email=user.email, disabled=user.disabled)  # fmt: skip

    def use_reset(self, reset_id: UUID, when: datetime) -> bool:
        row = self.resets[reset_id]
        if row["used_at"] is not None:
            return False
        row["used_at"] = when
        return True

    def void_resets(self, user_id: UUID, when: datetime) -> None:
        for row in self.resets.values():
            if row["user_id"] == user_id and row["used_at"] is None:
                row["used_at"] = when

    # ---- account management ---------------------------------------------------------------
    def list_sessions(self, user_id: UUID, *, limit: int, offset: int) -> Any:
        from podcast_engine.api.models.auth_model import SessionRead

        rows = sorted(self.tokens.values(), key=lambda t: t["created_at"], reverse=True)
        sessions = [
            SessionRead.model_validate(t)
            for t in rows
            if t["user_id"] == user_id and t["kind"] == "session" and t["revoked_at"] is None
        ]
        return page(sessions, limit, offset)

    def update_user(self, user_id: UUID, *, role: Any, disabled: bool | None) -> Any:
        from podcast_engine.api.models.auth_model import UserRead

        user = self.users.get(user_id)
        if user is None:
            return None
        changes = {k: v for k, v in {"role": role, "disabled": disabled}.items() if v is not None}
        self.users[user_id] = user.model_copy(update=changes)
        return UserRead.model_validate(self.users[user_id].model_dump())

    def set_email(self, user_id: UUID, email: str) -> None:
        from podcast_engine.api.errors import ConflictError

        other = self.find_user(email)
        if other is not None and other.user_id != user_id:
            raise ConflictError(f"an account with the email {email} already exists")
        self.users[user_id] = self.users[user_id].model_copy(update={"email": email})

    def count_admins(self) -> int:
        return sum(1 for u in self.users.values() if u.role == "admin" and not u.disabled)

    def delete_user(self, user_id: UUID) -> bool:
        if self.users.pop(user_id, None) is None:
            return False
        for token_id in [t for t, row in self.tokens.items() if row["user_id"] == user_id]:
            del self.tokens[token_id]
        for cascade in self.on_delete:
            cascade(user_id)
        return True


class FakeSecurityEventRepository:
    def __init__(self) -> None:
        self.rows: list[Any] = []

    def add(
        self, event: str, *, user_id: UUID | None, address: str, detail: dict[str, Any]
    ) -> None:
        from podcast_engine.api.models.auth_model import SecurityEventRead

        self.rows.insert(0, SecurityEventRead(
            event_id=uuid4(), user_id=user_id, event=event, address=address, detail=detail,
            created_at=datetime.now(UTC),
        ))  # fmt: skip

    def names(self) -> list[str]:
        """Event names, oldest first."""
        return [row.event for row in reversed(self.rows)]

    def list_page(self, *, user_id: UUID | None, event: str | None, limit: int, offset: int) -> Any:
        rows = [
            r
            for r in self.rows
            if (user_id is None or r.user_id == user_id) and (event is None or r.event == event)
        ]
        return page(rows, limit, offset)
