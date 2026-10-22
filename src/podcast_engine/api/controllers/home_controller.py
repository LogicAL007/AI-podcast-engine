"""HTTP-facing orchestration for the home document and API catalog."""

from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from podcast_engine.api.models.home_model import (
    CATALOG_PROFILE,
    JSON_HOME_MEDIA_TYPE,
    LINKSET_MEDIA_TYPE,
)
from podcast_engine.api.services.home_service import bearer_auth, build_catalog, build_home

CACHE = "public, max-age=300"  # it changes only when the API is redeployed


def public_base(request: Request) -> str:
    """The API's base URL as the client sees it, including a proxy's path prefix.

    nginx serves the API under ``/api`` and says so in ``X-Forwarded-Prefix``; scheme and host
    come from uvicorn's proxy-header handling.
    """
    prefix = request.headers.get("x-forwarded-prefix", "").rstrip("/")
    root = str(request.base_url).rstrip("/")
    return f"{root}{prefix}"


def discovery_links(base: str) -> str:
    """A ``Link`` header (RFC 8288) with the RFC 8631 and RFC 9727 relations."""
    return ", ".join(
        [
            f'<{base}/.well-known/api-catalog>; rel="api-catalog"',
            f'<{base}/openapi.json>; rel="service-desc"; type="application/vnd.oai.openapi+json"',
            f'<{base}/docs>; rel="service-doc"; type="text/html"',
            f'<{base}/health>; rel="status"',
        ]
    )


class HomeController:
    def __init__(self, *, token_days: int) -> None:
        self._token_days = token_days

    def home(self, request: Request, schema: dict[str, Any]) -> Response:
        """The home document, as ``application/json-home`` when the client asks for it."""
        base = public_base(request)
        document = build_home(
            schema, base=base, auth=bearer_auth(base=base, token_days=self._token_days)
        )
        accept = request.headers.get("accept", "")
        media_type = JSON_HOME_MEDIA_TYPE if JSON_HOME_MEDIA_TYPE in accept else "application/json"
        body = document.model_dump(mode="json", by_alias=True, exclude_none=True)
        # Nulls are left out (a resource has href or hrefTemplate, never both), but "no login" is
        # worth saying explicitly.
        body["api"]["auth"]["login"] = document.api.auth.login
        return JSONResponse(
            body,
            media_type=media_type,
            headers={"Link": discovery_links(base), "Cache-Control": CACHE, "Vary": "Accept"},
        )

    def catalog(self, request: Request, title: str, *, with_body: bool = True) -> Response:
        """The RFC 9727 catalog; HEAD answers with the headers only, as the RFC requires."""
        base = public_base(request)
        headers = {
            "Link": f'<{base}/.well-known/api-catalog>; rel="api-catalog"',
            "Cache-Control": CACHE,
        }
        media_type = f'{LINKSET_MEDIA_TYPE}; profile="{CATALOG_PROFILE}"'
        if not with_body:
            return Response(status_code=200, media_type=media_type, headers=headers)
        catalog = build_catalog(base=base, title=title)
        return JSONResponse(
            catalog.model_dump(mode="json", exclude_none=True),
            media_type=media_type,
            headers=headers,
        )
