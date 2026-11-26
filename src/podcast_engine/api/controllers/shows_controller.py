from uuid import UUID

from podcast_engine.api.errors import http_errors
from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.models.shows_model import ShowCreate, ShowRead, ShowUpdate
from podcast_engine.api.services.shows_service import ShowService


class ShowController:
    """HTTP-facing entry point for shows: calls the service and maps its errors to HTTP."""

    def __init__(self, service: ShowService) -> None:
        """Create the controller.

        Args:
            service: The show service holding the business rules.
        """
        self._service = service

    def create(self, data: ShowCreate, owner: UUID) -> ShowRead:
        """Create a show owned by the caller.

        Args:
            data: The new show's settings.
            owner: The signed-in user who will own it.

        Returns:
            The created show.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes (404 for another
                owner's show).
        """
        return http_errors(lambda: self._service.create(data, owner))

    def get(self, show_id: UUID, owner: UUID) -> ShowRead:
        """Return one of the caller's shows.

        Args:
            show_id: The show to return.
            owner: The signed-in user.

        Returns:
            The show's settings.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes (404 for another
                owner's show).
        """
        return http_errors(lambda: self._service.get(show_id, owner))

    def list_page(self, owner: UUID, *, limit: int, offset: int) -> Paged[ShowRead]:
        """Return one page of the caller's shows, newest first.

        Args:
            owner: The signed-in user.
            limit: Most shows to return.
            offset: Shows to skip before this page.

        Returns:
            The page of shows and the total across all pages.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes (404 for another
                owner's show).
        """
        return http_errors(lambda: self._service.list_page(owner, limit=limit, offset=offset))

    def update(self, show_id: UUID, owner: UUID, data: ShowUpdate) -> ShowRead:
        """Change some of a show's settings.

        Args:
            show_id: The show to change.
            owner: The signed-in user.
            data: The settings to change; fields left out keep their value.

        Returns:
            The show with its new settings.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes (404 for another
                owner's show).
        """
        return http_errors(lambda: self._service.update(show_id, owner, data))

    def delete(self, show_id: UUID, owner: UUID) -> None:
        """Delete one of the caller's shows and everything in it.

        Args:
            show_id: The show to delete.
            owner: The signed-in user.

        Raises:
            HTTPException: The service's domain errors, mapped to HTTP status codes (404 for another
                owner's show).
        """
        http_errors(lambda: self._service.delete(show_id, owner))
