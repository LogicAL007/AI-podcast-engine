from typing import Any

from pydantic import BaseModel, ConfigDict, Field

JSON_HOME_MEDIA_TYPE = "application/json-home"
LINKSET_MEDIA_TYPE = "application/linkset+json"
CATALOG_PROFILE = "https://www.rfc-editor.org/info/rfc9727"


class AuthScheme(BaseModel):
    """An HTTP authentication scheme the API accepts."""

    scheme: str = Field(description="An HTTP authentication scheme name", examples=["Bearer"])
    realms: list[str] = Field(default=[], description="Protection spaces it applies to")


class Hints(BaseModel):
    """How a resource can be used, as JSON Home resource hints."""

    model_config = ConfigDict(populate_by_name=True)

    allow: list[str] = Field(description="HTTP methods it supports", examples=[["GET", "PATCH"]])
    formats: dict[str, dict[str, Any]] = Field(
        description="Media types it returns", examples=[{"application/json": {}}]
    )
    accept_post: list[str] | None = Field(
        default=None, alias="acceptPost", description="Media types it accepts with POST"
    )
    accept_patch: list[str] | None = Field(
        default=None, alias="acceptPatch", description="Media types it accepts with PATCH"
    )
    accept_ranges: list[str] | None = Field(
        default=None, alias="acceptRanges", description="Range units it accepts (byte ranges)"
    )
    docs: str = Field(description="Human-readable documentation for it")
    auth_schemes: list[AuthScheme] = Field(
        alias="authSchemes", description="Authentication it requires; empty means none"
    )
    status: str | None = Field(default=None, description="`deprecated` if it is going away")


class Operation(BaseModel):
    """One operation on the resource (an addition to JSON Home)."""

    method: str = Field(description="HTTP method", examples=["GET"])
    summary: str = Field(description="What it does", examples=["Get an episode's audio"])
    operation_id: str = Field(alias="operationId", description="Its id in the OpenAPI description")
    paginated: bool = Field(description="Returns a page (`limit`, `offset`, `next`)")
    filters: list[str] = Field(description="Query parameters other than paging")
    authenticated: bool = Field(description="Accepts or needs a bearer token")
    success: list[int] = Field(description="Success status codes", examples=[[200]])
    errors: list[int] = Field(description="Error status codes it documents", examples=[[404]])
    docs: str = Field(description="This operation in the interactive documentation")


class Resource(BaseModel):
    """A JSON Home resource object: where it is and how to use it."""

    model_config = ConfigDict(populate_by_name=True)

    title: str = Field(description="What the resource is", examples=["Episode audio"])
    href: str | None = Field(default=None, description="Its URI, when it has no variables")
    href_template: str | None = Field(
        default=None,
        alias="hrefTemplate",
        description="Its URI template (RFC 6570), when it has variables",
        examples=["/v1/episodes/{episode_id}/audio.wav"],
    )
    href_vars: dict[str, str] | None = Field(
        default=None, alias="hrefVars", description="Each template variable and what it means"
    )
    hints: Hints
    operations: list[Operation] = Field(description="Its operations (an addition to JSON Home)")


class Auth(BaseModel):
    """How authentication works: whether it is needed, the schemes, and where to sign in."""

    required: bool = Field(description="Whether any request needs credentials")
    schemes: list[AuthScheme] = Field(description="Authentication schemes the API accepts")
    login: str | None = Field(description="Where to obtain credentials; null when there is none")
    api_keys: str | None = Field(default=None, description="Where to create API keys")
    token_lifetime_days: int | None = Field(
        default=None, description="How long a login token or API key works after it is issued"
    )
    note: str = Field(description="What a client should know")


class HealthLinks(BaseModel):
    """Where the liveness and readiness checks are."""

    live: str = Field(description="Liveness: the process is serving")
    ready: str = Field(description="Readiness: database, queue and storage answer")


class ApiInfo(BaseModel):
    """The home document's ``api`` object: title, links, auth, health and conventions.

    ``auth``, ``health`` and ``conventions`` are this API's own additions to JSON Home, which JSON
    Home clients ignore.
    """

    title: str = Field(description="The API's name")
    version: str = Field(description="The API's version")
    description: str = Field(description="What the API does")
    links: dict[str, str] = Field(
        description="Related documents by link relation (RFC 8631 and JSON Home's own)"
    )
    auth: Auth
    health: HealthLinks
    conventions: dict[str, str] = Field(description="Rules that apply to every endpoint")


class HomeDocument(BaseModel):
    """The API's home document: what it offers and how to use it, in one request.

    Follows "Home Documents for HTTP APIs" (draft-nottingham-json-home-06): an ``api`` object with
    the title and links, and ``resources`` keyed by link relation, each with a URI (or URI template)
    and hints such as the allowed methods and formats.
    """

    api: ApiInfo
    resources: dict[str, Resource] = Field(description="Every resource, keyed by link relation")


class LinkTarget(BaseModel):
    """One link in a Linkset: where it points, its media type and title."""

    href: str = Field(description="The linked resource")
    type: str | None = Field(default=None, description="Its media type")
    title: str | None = Field(default=None, description="What it is")


class LinkContext(BaseModel):
    """One Linkset entry: a context (``anchor``) and its links by relation."""

    model_config = ConfigDict(extra="allow")

    anchor: str = Field(description="The resource these links are about")


class ApiCatalog(BaseModel):
    """An RFC 9727 API catalog: a Linkset (RFC 9264) listing this publisher's APIs.

    Uses the link relations of RFC 8631.
    """

    linkset: list[LinkContext] = Field(description="The catalog and each API's links")
