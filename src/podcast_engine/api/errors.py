"""Domain errors raised by services and translated to HTTP by controllers."""

from collections.abc import Callable

from fastapi import HTTPException, status


class DomainError(Exception):
    """Base class for errors a service raises on purpose."""


class NotFoundError(DomainError):
    def __init__(self, resource: str, identifier: object) -> None:
        super().__init__(f"{resource} {identifier} not found")


class PipelineUnavailableError(DomainError):
    """The job queue could not be reached, so no work was started."""


class ConflictError(DomainError):
    """Valid, but not in the resource's current state (such as editing a running episode)."""


class InvalidInputError(DomainError):
    """The request is well-formed but refers to things that do not fit (an unknown speaker)."""


class PayloadTooLargeError(DomainError):
    """An upload is larger than the configured limit."""


class UnsupportedMediaTypeError(DomainError):
    """An upload is not a type the pipeline can read."""


def to_http(error: DomainError) -> HTTPException:
    """Map a domain error to the HTTP error the client should see."""
    if isinstance(error, NotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(error))
    if isinstance(error, PipelineUnavailableError):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error))
    if isinstance(error, ConflictError):
        return HTTPException(status.HTTP_409_CONFLICT, str(error))
    if isinstance(error, InvalidInputError):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))
    if isinstance(error, PayloadTooLargeError):
        return HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(error))
    if isinstance(error, UnsupportedMediaTypeError):
        return HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(error))
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Unexpected error")


def http_errors[T](call: Callable[[], T]) -> T:
    """Run a service call, turning a domain error into the HTTP error the client should see."""
    try:
        return call()
    except DomainError as error:
        raise to_http(error) from error
