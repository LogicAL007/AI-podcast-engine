from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response

from podcast_engine.api.controllers.home_controller import HomeController
from podcast_engine.api.dependencies import get_home_controller
from podcast_engine.api.models.home_model import (
    CATALOG_PROFILE,
    JSON_HOME_MEDIA_TYPE,
    LINKSET_MEDIA_TYPE,
    ApiCatalog,
    HomeDocument,
)

router = APIRouter(tags=["home"])

Controller = Annotated[HomeController, Depends(get_home_controller)]
LINK_HEADER = {
    "Link": {
        "description": "The API catalog, description, documentation and status (RFC 8631)",
        "schema": {"type": "string"},
    }
}


def _schema(request: Request) -> dict[str, Any]:
    """Return the app's OpenAPI schema, which lists the resources.

    Args:
        request: The incoming request, whose app builds the schema.

    Returns:
        The OpenAPI document.
    """
    schema: dict[str, Any] = request.app.openapi()
    return schema


@router.get(
    "/home",
    response_model=HomeDocument,
    summary="The API's home document",
    response_description="Every resource with how to use it, plus authentication and health",
    responses={
        200: {
            "content": {
                JSON_HOME_MEDIA_TYPE: {"schema": {"$ref": "#/components/schemas/HomeDocument"}}
            },
            "headers": LINK_HEADER,
        }
    },
)
def home(request: Request, controller: Controller) -> Response:
    """Start here.

    Lists every resource of the API with its URI or URI template, the methods it allows, the formats
    it returns and accepts, whether it supports byte ranges or paging, and a link to its
    documentation. Also says how authentication works (at present: it is not required), where the
    liveness and readiness checks are, and the conventions every endpoint follows.

    The format is a JSON home document (draft-nottingham-json-home). Ask for `application/json-home`
    to get that media type; otherwise it is served as `application/json`.

    \f

    Args:
        request: The incoming request.
        controller: The home controller, injected by FastAPI.

    Returns:
        The home document.
    """
    return controller.home(request, _schema(request))


@router.get("/", include_in_schema=False)
def root(request: Request, controller: Controller) -> Response:
    """The same home document at the root, where API clients conventionally look first.

    \f

    Args:
        request: The incoming request.
        controller: The home controller, injected by FastAPI.

    Returns:
        The home document.
    """
    return controller.home(request, _schema(request))


@router.get(
    "/.well-known/api-catalog",
    response_model=ApiCatalog,
    summary="The API catalog",
    response_description="A Linkset listing this API and its description, documentation and status",
    responses={
        200: {
            "content": {
                f'{LINKSET_MEDIA_TYPE}; profile="{CATALOG_PROFILE}"': {
                    "schema": {"$ref": "#/components/schemas/ApiCatalog"}
                }
            },
            "headers": LINK_HEADER,
        }
    },
)
def api_catalog(request: Request, controller: Controller) -> Response:
    """The API catalog at its well-known address (RFC 9727), for tools that discover APIs.

    A Linkset (RFC 9264) pointing to this API's home document, OpenAPI description, interactive
    documentation and status.

    \f

    Args:
        request: The incoming request.
        controller: The home controller, injected by FastAPI.

    Returns:
        The catalog.
    """
    return controller.catalog(request, request.app.title)


@router.head(
    "/.well-known/api-catalog",
    summary="Check the API catalog",
    description="Headers only, including the `api-catalog` link, as RFC 9727 requires.",
    response_description="The catalog exists",
    responses={200: {"headers": LINK_HEADER}},
)
def api_catalog_head(request: Request, controller: Controller) -> Response:
    """Answer HEAD for the API catalog with its headers only, as RFC 9727 requires.

    The route's OpenAPI description is set in its decorator.

    \f

    Args:
        request: The incoming request.
        controller: The home controller, injected by FastAPI.

    Returns:
        An empty response with the catalog's headers.
    """
    return controller.catalog(request, request.app.title, with_body=False)
