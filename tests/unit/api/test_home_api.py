"""The home document and API catalog: generated from the routes, in the standard formats."""

import re
from typing import Any

import pytest

from tests.unit.api.conftest import Harness

PREFIX = "tag:podcast-engine,2026:"


@pytest.fixture(scope="module")
def client_docs() -> tuple[Harness, dict[str, Any], dict[str, Any]]:
    harness = Harness()
    home = harness.client.get("/home").json()
    schema = harness.client.get("/openapi.json").json()
    return harness, home, schema


def test_home_is_json_or_json_home_with_discovery_links(harness: Harness) -> None:
    plain = harness.client.get("/home")
    assert plain.status_code == 200
    assert plain.headers["content-type"].startswith("application/json")
    assert plain.headers["vary"] == "Accept"
    assert "max-age" in plain.headers["cache-control"]
    for rel in ("api-catalog", "service-desc", "service-doc", "status"):
        assert f'rel="{rel}"' in plain.headers["link"]
    home = harness.client.get("/home", headers={"Accept": "application/json-home"})
    assert home.headers["content-type"].startswith("application/json-home")
    assert harness.client.get("/").json() == plain.json()


def test_every_endpoint_is_listed_with_its_methods(
    client_docs: tuple[Harness, dict[str, Any], dict[str, Any]],
) -> None:
    _, home, schema = client_docs
    by_path = {r.get("href") or r["hrefTemplate"]: r for r in home["resources"].values()}
    expected = {p for p in schema["paths"] if p not in {"/home", "/.well-known/api-catalog"}}
    assert set(by_path) == expected
    for path, resource in by_path.items():
        assert ("href" in resource) != ("hrefTemplate" in resource), path
        assert sorted(resource["hints"]["allow"]) == sorted(
            m.upper() for m in schema["paths"][path]
        )
        variables = re.findall(r"{(\w+)}", path)
        assert sorted(resource.get("hrefVars", {})) == sorted(variables), path
        assert resource["hints"]["docs"].startswith("http://testserver/docs#/")
        assert resource["hints"]["authSchemes"] == []
        assert {op["operationId"] for op in resource["operations"]} == {
            op["operationId"] for op in schema["paths"][path].values()
        }


def test_hints_say_how_to_use_each_resource(
    client_docs: tuple[Harness, dict[str, Any], dict[str, Any]],
) -> None:
    _, home, _ = client_docs
    resources = home["resources"]
    audio = resources[PREFIX + "episode-audio"]
    assert audio["hints"]["acceptRanges"] == ["bytes"]
    assert "audio/wav" in audio["hints"]["formats"]
    uploads = resources[PREFIX + "show-uploads"]
    assert uploads["hints"]["acceptPost"] == ["multipart/form-data"]
    script = resources[PREFIX + "episode-script"]
    assert script["hints"]["acceptPatch"] == ["application/json"]
    listing = next(
        op for op in resources[PREFIX + "episodes"]["operations"] if op["method"] == "GET"
    )
    assert listing["paginated"] is True
    assert set(listing["filters"]) == {"status", "show_id"}


def test_home_states_authentication_and_health(
    client_docs: tuple[Harness, dict[str, Any], dict[str, Any]],
) -> None:
    _, home, _ = client_docs
    auth = home["api"]["auth"]
    assert auth == {"required": False, "schemes": [], "login": None, "note": auth["note"]}
    assert "trusted network" in auth["note"]
    assert home["api"]["health"] == {
        "live": "http://testserver/health",
        "ready": "http://testserver/ready",
    }
    assert home["api"]["links"]["service-desc"] == "http://testserver/openapi.json"
    assert "pagination" in home["api"]["conventions"]


def test_links_include_the_proxy_prefix(harness: Harness) -> None:
    home = harness.client.get("/home", headers={"X-Forwarded-Prefix": "/api"}).json()
    assert home["api"]["links"]["service-doc"] == "http://testserver/api/docs"
    assert home["api"]["health"]["ready"] == "http://testserver/api/ready"


def test_api_catalog_follows_rfc_9727(harness: Harness) -> None:
    response = harness.client.get("/.well-known/api-catalog")
    assert response.status_code == 200
    content_type = response.headers["content-type"]
    assert content_type.startswith("application/linkset+json")
    assert 'profile="https://www.rfc-editor.org/info/rfc9727"' in content_type
    catalog, api = response.json()["linkset"]
    assert catalog["anchor"] == "http://testserver/.well-known/api-catalog"
    assert catalog["item"] == [{"href": "http://testserver/home", "title": "AI Podcast Engine"}]
    assert api["service-desc"][0]["href"] == "http://testserver/openapi.json"
    assert api["status"][0]["href"] == "http://testserver/health"
    assert {"service-doc", "service-meta"} <= set(api)


def test_api_catalog_head_answers_with_the_link_header(harness: Harness) -> None:
    response = harness.client.head("/.well-known/api-catalog")
    assert response.status_code == 200
    assert 'rel="api-catalog"' in response.headers["link"]
    assert response.content == b""
