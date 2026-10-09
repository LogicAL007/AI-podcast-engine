"""Domain errors raised by services and translated to HTTP by controllers."""

from fastapi import HTTPException, status


class DomainError(Exception):
    """Base class for errors a service raises on purpose."""


class NotFoundError(DomainError):
    def __init__(self, resource: str, identifier: object) -> None:
        super().__init__(f"{resource} {identifier} not found")


class PipelineUnavailableError(DomainError):
    """The job queue could not be reached, so no work was started."""


def to_http(error: DomainError) -> HTTPException:
    """Map a domain error to the HTTP error the client should see."""
    if isinstance(error, NotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(error))
    if isinstance(error, PipelineUnavailableError):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error))
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Unexpected error")
