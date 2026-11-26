from uuid import UUID

from podcast_engine.api.errors import DomainError, to_http
from podcast_engine.api.models.pagination_model import Paged
from podcast_engine.api.models.sources_model import SourceRead
from podcast_engine.api.services.sources_service import SourceService


class SourceController:
    """HTTP-facing entry point for a show's sources: calls the service, maps its errors to HTTP."""

    def __init__(self, service: SourceService) -> None:
        """Create the controller.

        Args:
            service: The source service holding the business rules.
        """
        self._service = service

    def list_for_show(
        self, show_id: UUID, owner: UUID, *, limit: int, offset: int
    ) -> Paged[SourceRead]:
        """Return one page of a show's source sections.

        Args:
            show_id: The show whose sources to list.
            owner: The signed-in user.
            limit: Most sections to return.
            offset: Sections to skip before this page.

        Returns:
            The page of sections, in source order, and the total.

        Raises:
            HTTPException: 404 when the show is not the caller's.
        """
        try:
            return self._service.list_for_show(show_id, owner, limit=limit, offset=offset)
        except DomainError as error:
            raise to_http(error) from error
