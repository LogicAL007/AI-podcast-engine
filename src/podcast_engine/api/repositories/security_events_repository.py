import json
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from podcast_engine.api.models.auth_model import SecurityEventRead
from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.common.logging import get_logger

log = get_logger("security")


class SecurityEventRepository(Protocol):
    """The security log: sign-ins, lockouts, password and token changes."""

    def add(
        self, event: str, *, user_id: UUID | None, address: str, detail: dict[str, Any]
    ) -> None:
        """Record one security event.

        Args:
            event: What happened, such as ``login_failed``.
            user_id: The account involved, if known.
            address: The client's IP address.
            detail: Anything else worth keeping about the event.
        """
        ...

    def list_page(
        self, *, user_id: UUID | None, event: str | None, limit: int, offset: int
    ) -> Paged[SecurityEventRead]:
        """Return one page of security events, newest first.

        Args:
            user_id: Only this account's events, or all when None.
            event: Only events of this kind, or all when None.
            limit: Most events to return.
            offset: Events to skip before this page.

        Returns:
            The page of events, newest first, and the total across all pages.
        """
        ...


class PostgresSecurityEventRepository:
    """The security log in the ``security_events`` table; the only code that knows it.

    Writes commit on their own. Each event also goes to the structured log, for shipping elsewhere.
    """

    def __init__(self, session: Session) -> None:
        """Create the repository.

        Args:
            session: The database session for this request.
        """
        self._session = session

    def add(
        self, event: str, *, user_id: UUID | None, address: str, detail: dict[str, Any]
    ) -> None:
        """Record one security event, in the structured log and the table.

        A failure to store it is rolled back and logged, never raised into the request: the log must
        never break sign-in.

        Args:
            event: What happened, such as ``login_failed``.
            user_id: The account involved, if known.
            address: The client's IP address.
            detail: Anything else worth keeping about the event.
        """
        log.info("security_event", security_event=event, user_id=str(user_id) if user_id else None,
                 address=address, **detail)  # fmt: skip
        try:
            self._session.execute(
                text(
                    "INSERT INTO security_events (user_id, event, address, detail)"
                    " VALUES (:user_id, :event, :address, CAST(:detail AS jsonb))"
                ),
                {
                    "user_id": user_id,
                    "event": event,
                    "address": address,
                    "detail": json.dumps(detail),
                },
            )
            self._session.commit()
        except Exception:
            self._session.rollback()
            log.exception("security_event_not_stored", security_event=event)

    def list_page(
        self, *, user_id: UUID | None, event: str | None, limit: int, offset: int
    ) -> Paged[SecurityEventRead]:
        """Return one page of security events, newest first.

        Args:
            user_id: Only this account's events, or all when None.
            event: Only events of this kind, or all when None.
            limit: Most events to return.
            offset: Events to skip before this page.

        Returns:
            The page of events, newest first, and the total across all pages.
        """
        where = ["TRUE"]
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if user_id is not None:
            where.append("user_id = :user_id")
            params["user_id"] = user_id
        if event is not None:
            where.append("event = :event")
            params["event"] = event
        condition = " AND ".join(where)
        rows = self._session.execute(
            text(
                "SELECT event_id, user_id, event, address, detail, created_at"  # noqa: S608
                f" FROM security_events WHERE {condition}"
                " ORDER BY created_at DESC, event_id LIMIT :limit OFFSET :offset"
            ),
            params,
        ).mappings()
        items = [SecurityEventRead.model_validate(row) for row in rows]
        total = self._session.execute(
            text(f"SELECT count(*) FROM security_events WHERE {condition}"),  # noqa: S608
            params,
        ).scalar_one()
        return Paged(items, int(total))
