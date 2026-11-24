from collections.abc import Callable

from fastapi import HTTPException, status


class DomainError(Exception):
    """Base class for errors a service raises on purpose."""


class NotFoundError(DomainError):
    """The resource does not exist, or belongs to someone else."""

    def __init__(self, resource: str, identifier: object) -> None:
        """Create the error.

        Args:
            resource: What was looked for, such as ``show``.
            identifier: Its id.
        """
        super().__init__(f"{resource} {identifier} not found")


class PipelineUnavailableError(DomainError):
    """The job queue could not be reached, so no work was started."""


class UnauthenticatedError(DomainError):
    """No credentials, or ones that are wrong, expired or revoked."""


class ForbiddenError(DomainError):
    """Authenticated, but not allowed to do this."""


class AuthNotConfiguredError(DomainError):
    """The token key is missing (Vault not set up), so no token can be checked."""


class TooManyRequestsError(DomainError):
    """Too many attempts from this address; try again after ``retry_after`` seconds."""

    def __init__(self, message: str, retry_after: int) -> None:
        """Create the error.

        Args:
            message: What the client should be told.
            retry_after: Seconds until the client may try again.
        """
        super().__init__(message)
        self.retry_after = retry_after


class ConflictError(DomainError):
    """Valid, but not in the resource's current state (such as editing a running episode)."""


class InvalidInputError(DomainError):
    """The request is well-formed but refers to things that do not fit (an unknown speaker)."""


class PayloadTooLargeError(DomainError):
    """An upload is larger than the configured limit."""


class UnsupportedMediaTypeError(DomainError):
    """An upload is not a type the pipeline can read."""


def to_http(error: DomainError) -> HTTPException:
    """Map a domain error to the HTTP error the client should see.

    401 adds a ``WWW-Authenticate`` header and 429 a ``Retry-After`` header. An error with no
    mapping becomes a 500 that says nothing about it.

    Args:
        error: The error a service raised.

    Returns:
        The HTTP exception to raise.
    """
    if isinstance(error, UnauthenticatedError):
        return HTTPException(
            status.HTTP_401_UNAUTHORIZED, str(error), headers={"WWW-Authenticate": "Bearer"}
        )
    if isinstance(error, TooManyRequestsError):
        return HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            str(error),
            headers={"Retry-After": str(error.retry_after)},
        )
    if isinstance(error, ForbiddenError):
        return HTTPException(status.HTTP_403_FORBIDDEN, str(error))
    if isinstance(error, AuthNotConfiguredError):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error))
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
    """Run a service call, turning a domain error into the HTTP error the client should see.

    Args:
        call: The service call to run.

    Returns:
        Whatever the call returns.

    Raises:
        HTTPException: The call raised a domain error.
    """
    try:
        return call()
    except DomainError as error:
        raise to_http(error) from error
