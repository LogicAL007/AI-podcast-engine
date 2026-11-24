from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from podcast_engine.api.controllers.ops_controller import OpsController
from podcast_engine.api.dependencies import get_ops_controller
from podcast_engine.api.models.ops_model import Health, Readiness

router = APIRouter(tags=["ops"])

Controller = Annotated[OpsController, Depends(get_ops_controller)]


@router.get(
    "/health",
    response_model=Health,
    summary="Liveness check",
    response_description="The process is up",
)
def health(controller: Controller) -> Health:
    """Answers while the process is serving.

    Does not check the database, queue or storage: use the readiness check for that.

    \f

    Args:
        controller: The ops controller, injected by FastAPI.

    Returns:
        Status ``ok`` and the API version.
    """
    return controller.health()


@router.get(
    "/ready",
    response_model=Readiness,
    summary="Readiness check",
    response_description="Every dependency answered",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": Readiness,
            "description": "A dependency did not answer; `checks` says which",
        }
    },
)
def ready(controller: Controller, response: Response) -> Readiness:
    """Checks that the database, the job queue and object storage answer.

    A load balancer then sends traffic only to an API that can do its work.

    \f

    Args:
        controller: The ops controller, injected by FastAPI.
        response: The response, whose status is set to 503 when a check fails.

    Returns:
        ``ready`` or ``not ready``, with each dependency's result.
    """
    result = controller.readiness()
    if result.status != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
