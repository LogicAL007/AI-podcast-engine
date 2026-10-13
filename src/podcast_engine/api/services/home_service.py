"""Builds the home document and API catalog from the API's own OpenAPI description.

Generating them from the routes keeps them true: a new endpoint appears in the home document as soon
as it exists, with the methods, formats and documentation link its route declares.
"""

import re
from typing import Any

from podcast_engine.api.models.home_model import (
    ApiCatalog,
    ApiInfo,
    Auth,
    HealthLinks,
    Hints,
    HomeDocument,
    LinkContext,
    LinkTarget,
    Operation,
    Resource,
)

# Link relations for this API's resources: tag URIs (RFC 4151), as the JSON Home draft suggests
# for relations that are not registered.
RELATION_PREFIX = "tag:podcast-engine,2026:"
PAGING = {"limit", "offset"}
METHOD_ORDER = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"]
# Not resources a client navigates to: the documents themselves and the docs UI.
EXCLUDED = {"/home", "/.well-known/api-catalog"}
LICENSE = "https://spdx.org/licenses/MIT.html"

CONVENTIONS = {
    "pagination": (
        "Lists return {items, total, limit, offset, next}; limit is 1-100 (default 20), offset "
        "is 0 or more, and next is the following page's path, or null on the last page."
    ),
    "errors": (
        'Errors are JSON {"detail": "..."}; 422 validation errors list each problem in detail.'
    ),
    "identifiers": "Shows, episodes, claims and uploads are identified by UUIDs.",
    "time": "Timestamps are ISO 8601 in UTC.",
    "disclosure": "Every episode is labelled AI-generated in its audio, show notes and feed.",
}


def relation_for(path: str) -> str:
    """A resource's link relation from its path: a segment followed by an id is singular.

    ``/shows/{show_id}/episodes`` -> ``tag:podcast-engine,2026:show-episodes``;
    ``/episodes/{episode_id}/audio.wav`` -> ``...:episode-audio``.
    """
    segments = path.strip("/").split("/")
    names = []
    for n, segment in enumerate(segments):
        if not segment or segment.startswith("{"):
            continue
        name = re.sub(r"\.(wav|md|xml|json)$", "", segment).replace("_", "-")
        followed_by_id = n + 1 < len(segments) and segments[n + 1].startswith("{")
        names.append(name[:-1] if followed_by_id and name.endswith("s") else name)
    return RELATION_PREFIX + ("-".join(names) or "root")


def _media_types(responses: dict[str, Any], *, success: bool) -> list[str]:
    types: list[str] = []
    for code, response in responses.items():
        if code.startswith(("2", "3")) == success:
            types += list((response.get("content") or {}).keys())
    return list(dict.fromkeys(types))


def build_home(schema: dict[str, Any], *, base: str, auth_required: bool = False) -> HomeDocument:
    """The home document for an OpenAPI description. ``base`` is the API's public base URL."""
    info = schema["info"]
    resources: dict[str, Resource] = {}
    for path, operations in schema["paths"].items():
        if path in EXCLUDED:
            continue
        methods = {method.upper(): op for method, op in operations.items()}
        ordered = sorted(methods, key=lambda m: METHOD_ORDER.index(m) if m in METHOD_ORDER else 99)
        variables = re.findall(r"{(\w+)}", path)
        listed: list[Operation] = []
        formats: list[str] = []
        accept_post = accept_patch = None
        ranges = False
        primary = methods.get("GET") or methods[ordered[0]]
        for method in ordered:
            op = methods[method]
            params = op.get("parameters", [])
            queries = [p["name"] for p in params if p["in"] == "query"]
            ranges = ranges or any(
                p["in"] == "header" and p["name"].lower() == "range" for p in params
            )
            formats += _media_types(op["responses"], success=True)
            body_types = list((op.get("requestBody") or {}).get("content", {}).keys())
            if method == "POST" and body_types:
                accept_post = body_types
            if method == "PATCH" and body_types:
                accept_patch = body_types
            tag = (op.get("tags") or ["default"])[0]
            listed.append(
                Operation(
                    method=method,
                    summary=op.get("summary", ""),
                    operationId=op["operationId"],
                    paginated=set(queries) >= PAGING,
                    filters=[q for q in queries if q not in PAGING],
                    success=sorted(int(c) for c in op["responses"] if c[0] in "23"),
                    errors=sorted(int(c) for c in op["responses"] if c[0] in "45"),
                    docs=f"{base}/docs#/{tag}/{op['operationId']}",
                )
            )
        hints = Hints(
            allow=ordered,
            formats={media: {} for media in dict.fromkeys(formats)},
            accept_post=accept_post,
            accept_patch=accept_patch,
            accept_ranges=["bytes"] if ranges else None,
            docs=listed[ordered.index("GET") if "GET" in ordered else 0].docs,
            auth_schemes=[],
            status="deprecated" if all(op.get("deprecated") for op in methods.values()) else None,
        )
        resource = Resource(
            title=primary.get("summary", path),
            hints=hints,
            operations=listed,
            **(
                {
                    "hrefTemplate": path,
                    "hrefVars": {v: f"{RELATION_PREFIX}param:{v}" for v in variables},
                }
                if variables
                else {"href": path}
            ),
        )
        resources[relation_for(path)] = resource

    auth = Auth(
        required=auth_required,
        schemes=[],
        login=None,
        note=(
            "No authentication: every endpoint is open. Run the API only on a trusted network "
            "(the compose stack binds it to localhost)."
        ),
    )
    api = ApiInfo(
        title=info["title"],
        version=info["version"],
        description=info.get("summary") or info.get("description", "").strip().split("\n")[0],
        links={
            "service-desc": f"{base}/openapi.json",
            "service-doc": f"{base}/docs",
            "status": f"{base}/health",
            "api-catalog": f"{base}/.well-known/api-catalog",
            "describedBy": f"{base}/openapi.json",
            "license": LICENSE,
        },
        auth=auth,
        health=HealthLinks(live=f"{base}/health", ready=f"{base}/ready"),
        conventions=CONVENTIONS,
    )
    return HomeDocument(api=api, resources=resources)


def build_catalog(*, base: str, title: str) -> ApiCatalog:
    """The RFC 9727 catalog: this publisher has one API, described by these documents."""
    return ApiCatalog(
        linkset=[
            LinkContext(
                anchor=f"{base}/.well-known/api-catalog",
                item=[LinkTarget(href=f"{base}/home", title=title).model_dump(exclude_none=True)],
            ),
            LinkContext(
                anchor=f"{base}/home",
                **{
                    "service-desc": [
                        {"href": f"{base}/openapi.json", "type": "application/vnd.oai.openapi+json"}
                    ],
                    "service-doc": [{"href": f"{base}/docs", "type": "text/html"}],
                    "service-meta": [{"href": f"{base}/home", "type": "application/json-home"}],
                    "status": [{"href": f"{base}/health", "type": "application/json"}],
                },
            ),
        ]
    )
