"""Persistence for shows: the only module that knows the ``shows`` table."""

import json
from collections.abc import Mapping
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from podcast_engine.api.models.shows_model import ShowCreate, ShowRead

_COLUMNS = (
    "show_id, topic, tone, target_minutes, host_count, language, expertise, sources, created_at"
)
_INSERT = (
    "INSERT INTO shows (topic, tone, target_minutes, host_count, language, expertise, sources)"
    " VALUES (:topic, :tone, :target_minutes, :host_count, :language, :expertise,"
    " CAST(:sources AS jsonb))"
    " RETURNING show_id, topic, tone, target_minutes, host_count, language, expertise,"
    " sources, created_at"
)
_UPDATABLE = frozenset(
    {"topic", "tone", "target_minutes", "host_count", "language", "expertise", "sources"}
)


class ShowRepository(Protocol):
    def add(self, data: ShowCreate) -> ShowRead: ...

    def get(self, show_id: UUID) -> ShowRead | None: ...

    def list_page(self, *, limit: int, offset: int) -> list[ShowRead]: ...

    def update(self, show_id: UUID, changes: Mapping[str, Any]) -> ShowRead | None: ...

    def delete(self, show_id: UUID) -> bool: ...


class PostgresShowRepository:
    """Each write commits on its own, so callers can act on the result straight away."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, data: ShowCreate) -> ShowRead:
        row = (
            self._session.execute(
                text(_INSERT),
                _to_params(data.model_dump(mode="json")),
            )
            .mappings()
            .one()
        )
        self._session.commit()
        return ShowRead.model_validate(row)

    def get(self, show_id: UUID) -> ShowRead | None:
        row = (
            self._session.execute(
                text(f"SELECT {_COLUMNS} FROM shows WHERE show_id = :show_id"),  # noqa: S608
                {"show_id": show_id},
            )
            .mappings()
            .one_or_none()
        )
        return ShowRead.model_validate(row) if row else None

    def list_page(self, *, limit: int, offset: int) -> list[ShowRead]:
        rows = self._session.execute(
            text(
                f"SELECT {_COLUMNS} FROM shows"  # noqa: S608 - constant column list
                " ORDER BY created_at DESC, show_id LIMIT :limit OFFSET :offset"
            ),
            {"limit": limit, "offset": offset},
        ).mappings()
        return [ShowRead.model_validate(row) for row in rows]

    def update(self, show_id: UUID, changes: Mapping[str, Any]) -> ShowRead | None:
        unknown = set(changes) - _UPDATABLE
        if unknown:
            raise ValueError(f"not updatable: {sorted(unknown)}")
        # Column names come from the whitelist above; values are always bound parameters.
        assignments = ", ".join(
            f"{column} = CAST(:{column} AS jsonb)"
            if column == "sources"
            else f"{column} = :{column}"
            for column in changes
        )
        row = (
            self._session.execute(
                text(
                    f"UPDATE shows SET {assignments} WHERE show_id = :show_id"  # noqa: S608
                    f" RETURNING {_COLUMNS}"
                ),
                {**_to_params(changes), "show_id": show_id},
            )
            .mappings()
            .one_or_none()
        )
        self._session.commit()
        return ShowRead.model_validate(row) if row else None

    def delete(self, show_id: UUID) -> bool:
        result = self._session.execute(
            text("DELETE FROM shows WHERE show_id = :show_id"), {"show_id": show_id}
        )
        self._session.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]


def _to_params(values: Mapping[str, Any]) -> dict[str, Any]:
    """Serialise the jsonb column; everything else binds as-is."""
    params = dict(values)
    if "sources" in params:
        params["sources"] = json.dumps([str(url) for url in params["sources"]])
    return params
