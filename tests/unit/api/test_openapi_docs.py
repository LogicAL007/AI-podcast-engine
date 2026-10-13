"""The API documentation is part of the contract: every route must describe itself fully."""

from typing import Any

import pytest

from tests.unit.api.conftest import Harness

ERROR_REF = "#/components/schemas/ErrorDetail"
# Error responses that deliberately return a domain body instead of ErrorDetail.
OWN_ERROR_BODY = {("/ready", "503"): "#/components/schemas/Readiness"}


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return Harness().client.get("/openapi.json").json()  # type: ignore[no-any-return]


def operations(schema: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (method, path, op) for path, ops in schema["paths"].items() for method, op in ops.items()
    ]


def test_every_operation_has_a_summary_description_and_named_id(schema: dict[str, Any]) -> None:
    for method, path, op in operations(schema):
        where = f"{method.upper()} {path}"
        assert op.get("summary"), f"{where}: no summary"
        assert op.get("description"), f"{where}: no description (write a docstring)"
        assert op["operationId"].isidentifier(), f"{where}: operationId {op['operationId']!r}"
        assert "__" not in op["operationId"], f"{where}: FastAPI's default generated id"
        assert op.get("tags"), f"{where}: no tag"


def test_operation_ids_are_unique(schema: dict[str, Any]) -> None:
    ids = [op["operationId"] for *_, op in operations(schema)]
    assert len(ids) == len(set(ids))


def test_every_parameter_is_described(schema: dict[str, Any]) -> None:
    for method, path, op in operations(schema):
        for parameter in op.get("parameters", []):
            assert parameter.get("description"), (
                f"{method.upper()} {path}: {parameter['name']} undescribed"
            )


def test_every_error_response_uses_the_error_schema(schema: dict[str, Any]) -> None:
    for method, path, op in operations(schema):
        for code, response in op["responses"].items():
            assert response.get("description"), f"{method.upper()} {path} {code}: no description"
            if code.startswith(("4", "5")) and code != "422":  # 422 is FastAPI's validation schema
                ref = response["content"]["application/json"]["schema"]["$ref"]
                expected = OWN_ERROR_BODY.get((path, code), ERROR_REF)
                assert ref == expected, f"{method.upper()} {path} {code}: {ref}"


def test_every_tag_is_described(schema: dict[str, Any]) -> None:
    described = {tag["name"] for tag in schema["tags"] if tag.get("description")}
    used = {tag for *_, op in operations(schema) for tag in op["tags"]}
    assert used <= described


def test_request_and_response_fields_are_described(schema: dict[str, Any]) -> None:
    for name in (
        "ShowCreate",
        "ShowRead",
        "EpisodeRead",
        "EpisodeLinks",
        "ClaimRead",
        "StageRunRead",
    ):
        for field, spec in schema["components"]["schemas"][name]["properties"].items():
            assert spec.get("description"), f"{name}.{field} undescribed"
    assert schema["components"]["schemas"]["ShowCreate"]["examples"]


def test_audio_is_documented_as_a_binary_file_with_ranges(schema: dict[str, Any]) -> None:
    op = schema["paths"]["/episodes/{episode_id}/audio.wav"]["get"]
    assert op["responses"]["200"]["content"]["audio/wav"]["schema"] == {
        "type": "string",
        "format": "binary",
    }
    assert {"200", "206", "404", "416"} <= set(op["responses"])
    assert "Range" in {p["name"] for p in op["parameters"]}
    assert "head" in schema["paths"]["/episodes/{episode_id}/audio.wav"]


def test_episode_links_are_in_the_response_schema(schema: dict[str, Any]) -> None:
    properties = schema["components"]["schemas"]["EpisodeRead"]["properties"]
    assert "links" in properties
    assert "has_audio" not in properties
