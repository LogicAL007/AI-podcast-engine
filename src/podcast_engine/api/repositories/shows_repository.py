import json
from collections.abc import Mapping
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.models.shows_model import ShowCreate, ShowRead

_COLUMNS = (
    "show_id, topic, tone, target_minutes, host_count, language, expertise, sources,"
    " search_queries, topic_keywords, attribution, max_segments, ranking_profile,"
    " review_before_voice, host_voices, host_effects, music, created_at"
)
_INSERT = (
    "INSERT INTO shows (topic, tone, target_minutes, host_count, language, expertise, sources,"  # noqa: S608
    " search_queries, topic_keywords, attribution, max_segments, ranking_profile,"
    " review_before_voice, host_voices, host_effects, music, owner_id)"
    " VALUES (:topic, :tone, :target_minutes, :host_count, :language, :expertise,"
    " CAST(:sources AS jsonb), CAST(:search_queries AS jsonb), :topic_keywords, :attribution,"
    " :max_segments, :ranking_profile, :review_before_voice, CAST(:host_voices AS jsonb),"
    " CAST(:host_effects AS jsonb), CAST(:music AS jsonb), :owner_id)"
    f" RETURNING {_COLUMNS}"
)
_JSON_COLUMNS = frozenset({"sources", "search_queries", "host_voices", "host_effects", "music"})
_UPDATABLE = frozenset(
    {
        "topic",
        "tone",
        "target_minutes",
        "host_count",
        "language",
        "expertise",
        "sources",
        "search_queries",
        "topic_keywords",
        "attribution",
        "max_segments",
        "ranking_profile",
        "review_before_voice",
        "host_voices",
        "host_effects",
        "music",
    }
)


class ShowRepository(Protocol):
    """Stores shows.

    Every method is scoped to one owner: another user's show does not exist for them.
    """

    def add(self, data: ShowCreate, owner_id: UUID) -> ShowRead:
        """Create a show.

        Args:
            data: The new show's settings.
            owner_id: The user who will own it.

        Returns:
            The created show.
        """
        ...

    def get(self, show_id: UUID, owner_id: UUID) -> ShowRead | None:
        """Return one of the user's shows.

        Args:
            show_id: The show.
            owner_id: The user asking.

        Returns:
            The show, or None when the user has no such show.
        """
        ...

    def list_page(self, owner_id: UUID, *, limit: int, offset: int) -> Paged[ShowRead]:
        """Return one page of the user's shows, newest first.

        Args:
            owner_id: The user asking.
            limit: Most shows to return.
            offset: Shows to skip before this page.

        Returns:
            The page of shows, newest first, and the total.
        """
        ...

    def update(self, show_id: UUID, owner_id: UUID, changes: Mapping[str, Any]) -> ShowRead | None:
        """Change some of a show's settings.

        Args:
            show_id: The show.
            owner_id: The user asking.
            changes: The columns to change and their new values.

        Returns:
            The show after the change, or None when the user has no such show.
        """
        ...

    def delete(self, show_id: UUID, owner_id: UUID) -> bool:
        """Delete a show and, by cascade, everything in it.

        Args:
            show_id: The show.
            owner_id: The user asking.

        Returns:
            True if a show was deleted.
        """
        ...

    def claim_unowned(self, owner_id: UUID) -> int:
        """Give shows made before login existed to this user.

        Args:
            owner_id: The user to give them to.

        Returns:
            How many shows were claimed.
        """
        ...

    def stored_files(
        self, *, owner_id: UUID | None = None, show_id: UUID | None = None
    ) -> list[str]:
        """Return the object-storage keys of the files under a user's shows (or one show).

        Args:
            owner_id: Every show of this user, or None.
            show_id: This show only, or None.

        Returns:
            The object keys of their files.
        """
        ...


class PostgresShowRepository:
    """Shows in the ``shows`` table, the only code that knows it.

    Each write commits on its own, so callers can act on the result straight away.
    """

    def __init__(self, session: Session) -> None:
        """Create the repository.

        Args:
            session: The database session for this request.
        """
        self._session = session

    def add(self, data: ShowCreate, owner_id: UUID) -> ShowRead:
        """Create a show.

        Args:
            data: The new show's settings.
            owner_id: The user who will own it.

        Returns:
            The created show.
        """
        row = (
            self._session.execute(
                text(_INSERT),
                {**_to_params(data.model_dump(mode="json")), "owner_id": owner_id},
            )
            .mappings()
            .one()
        )
        self._session.commit()
        return ShowRead.model_validate(row)

    def get(self, show_id: UUID, owner_id: UUID) -> ShowRead | None:
        """Return one of the user's shows.

        Args:
            show_id: The show.
            owner_id: The user asking.

        Returns:
            The show, or None when the user has no such show.
        """
        row = (
            self._session.execute(
                text(
                    f"SELECT {_COLUMNS} FROM shows"  # noqa: S608 - constant column list
                    " WHERE show_id = :show_id AND owner_id = :owner_id"
                ),
                {"show_id": show_id, "owner_id": owner_id},
            )
            .mappings()
            .one_or_none()
        )
        return ShowRead.model_validate(row) if row else None

    def list_page(self, owner_id: UUID, *, limit: int, offset: int) -> Paged[ShowRead]:
        """Return one page of the user's shows, newest first.

        Args:
            owner_id: The user asking.
            limit: Most shows to return.
            offset: Shows to skip before this page.

        Returns:
            The page of shows, newest first, and the total.
        """
        params = {"owner_id": owner_id, "limit": limit, "offset": offset}
        rows = self._session.execute(
            text(
                f"SELECT {_COLUMNS} FROM shows WHERE owner_id = :owner_id"  # noqa: S608
                " ORDER BY created_at DESC, show_id LIMIT :limit OFFSET :offset"
            ),
            params,
        ).mappings()
        total = self._session.execute(
            text("SELECT count(*) FROM shows WHERE owner_id = :owner_id"), params
        ).scalar_one()
        return Paged([ShowRead.model_validate(row) for row in rows], int(total))

    def update(self, show_id: UUID, owner_id: UUID, changes: Mapping[str, Any]) -> ShowRead | None:
        """Change some of a show's settings.

        Column names come from a fixed whitelist; values are always bound parameters.

        Args:
            show_id: The show.
            owner_id: The user asking.
            changes: The columns to change and their new values.

        Returns:
            The show after the change, or None when the user has no such show.
        """
        unknown = set(changes) - _UPDATABLE
        if unknown:
            raise ValueError(f"not updatable: {sorted(unknown)}")
        assignments = ", ".join(
            f"{column} = CAST(:{column} AS jsonb)"
            if column in _JSON_COLUMNS
            else f"{column} = :{column}"
            for column in changes
        )
        row = (
            self._session.execute(
                text(
                    f"UPDATE shows SET {assignments}"  # noqa: S608
                    " WHERE show_id = :show_id AND owner_id = :owner_id"
                    f" RETURNING {_COLUMNS}"
                ),
                {**_to_params(changes), "show_id": show_id, "owner_id": owner_id},
            )
            .mappings()
            .one_or_none()
        )
        self._session.commit()
        return ShowRead.model_validate(row) if row else None

    def delete(self, show_id: UUID, owner_id: UUID) -> bool:
        """Delete a show and, by cascade, everything in it.

        Args:
            show_id: The show.
            owner_id: The user asking.

        Returns:
            True if a show was deleted.
        """
        result = self._session.execute(
            text("DELETE FROM shows WHERE show_id = :show_id AND owner_id = :owner_id"),
            {"show_id": show_id, "owner_id": owner_id},
        )
        self._session.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]

    def claim_unowned(self, owner_id: UUID) -> int:
        """Give shows made before login existed to this user (the first admin).

        Args:
            owner_id: The user to give them to.

        Returns:
            How many shows were claimed.
        """
        result = self._session.execute(
            text("UPDATE shows SET owner_id = :owner_id WHERE owner_id IS NULL"),
            {"owner_id": owner_id},
        )
        self._session.commit()
        return int(result.rowcount)  # type: ignore[attr-defined]

    def stored_files(
        self, *, owner_id: UUID | None = None, show_id: UUID | None = None
    ) -> list[str]:
        """Return every object-storage key belonging to the owner's shows (or one show).

        Episode audio (WAV and MP3) and notes, uploaded PDFs, and the shows' feeds. Read before
        deleting rows, so the files can be removed too.

        Args:
            owner_id: Every show of this user, or None.
            show_id: This show only, or None.

        Returns:
            The object keys of their files.
        """
        if (owner_id is None) == (show_id is None):
            raise ValueError("give exactly one of owner_id or show_id")
        scope = "s.owner_id = :id" if owner_id is not None else "s.show_id = :id"
        query = (  # noqa: S608, UP032
            "SELECT k FROM (SELECT unnest(ARRAY[e.audio_key, e.audio_mp3_key, e.notes_key]) AS k"
            " FROM episodes e JOIN shows s ON s.show_id = e.show_id WHERE {scope}"
            " UNION ALL SELECT u.object_key"
            " FROM uploads u JOIN shows s ON s.show_id = u.show_id WHERE {scope}"
            " UNION ALL SELECT 'feeds/' || s.show_id || '.xml' FROM shows s WHERE {scope}) keys"
            " WHERE k IS NOT NULL"
        ).format(scope=scope)
        rows = self._session.execute(
            text(query),
            {"id": owner_id or show_id},
        )
        return [row.k for row in rows]


def _to_params(values: Mapping[str, Any]) -> dict[str, Any]:
    """Serialise the jsonb columns for binding; everything else binds as it is.

    The jsonb values are already plain JSON, from ``model_dump(mode="json")``.

    Args:
        values: Column values.

    Returns:
        The values with jsonb columns as JSON text.
    """
    params = dict(values)
    if "sources" in params:
        params["sources"] = json.dumps([str(url) for url in params["sources"]])
    if "search_queries" in params:
        params["search_queries"] = json.dumps(list(params["search_queries"]))
    if "host_voices" in params:
        params["host_voices"] = json.dumps({h: str(v) for h, v in params["host_voices"].items()})
    for column in ("host_effects", "music"):
        if column in params:
            params[column] = json.dumps(params[column])
    return params
