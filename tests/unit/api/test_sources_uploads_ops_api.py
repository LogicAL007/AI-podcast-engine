from datetime import UTC, datetime
from uuid import UUID, uuid4

from podcast_engine.api.models.sources_model import SourceRead
from podcast_engine.common.models import ReliabilityTier
from tests.unit.api.conftest import MAX_UPLOAD_BYTES, Harness

PDF = b"%PDF-1.7\n% a tiny but well-labelled pdf\n"


def _show(harness: Harness) -> UUID:
    return UUID(
        harness.client.post("/v1/shows", json={"topic": "Uploaded sources"}).json()["show_id"]
    )


def test_sources_are_listed_in_order_with_paging(harness: Harness) -> None:
    show_id = _show(harness)
    harness.sources.rows[show_id] = [
        SourceRead(
            item_id=uuid4(),
            url=f"https://x.test/#s{n}",
            title=f"Section {n}",
            position=n,
            reliability=ReliabilityTier.PRIMARY,
            content_hash="h",
            words=50,
            chunks=2,
            published_at=None,
            fetched_at=datetime.now(UTC),
        )
        for n in range(3)
    ]
    body = harness.client.get(f"/v1/shows/{show_id}/sources", params={"limit": 2}).json()
    assert [s["title"] for s in body["items"]] == ["Section 0", "Section 1"]
    assert body["total"] == 3
    assert harness.client.get(f"/v1/shows/{uuid4()}/sources").status_code == 404


def test_upload_a_pdf_list_download_and_delete_it(harness: Harness) -> None:
    show_id = _show(harness)
    created = harness.client.post(
        f"/v1/shows/{show_id}/uploads", files={"file": ("../My Report.pdf", PDF, "application/pdf")}
    )
    assert created.status_code == 201, created.text
    upload = created.json()
    assert upload["filename"] == "My Report.pdf"
    assert upload["size_bytes"] == len(PDF)
    assert "object_key" not in upload

    listed = harness.client.get(f"/v1/shows/{show_id}/uploads").json()
    assert [u["upload_id"] for u in listed["items"]] == [upload["upload_id"]]

    download = harness.client.get(upload["file"])
    assert download.status_code == 200
    assert download.content == PDF
    assert download.headers["content-type"] == "application/pdf"
    assert "My%20Report.pdf" in download.headers["content-disposition"]

    assert (
        harness.client.delete(f"/v1/shows/{show_id}/uploads/{upload['upload_id']}").status_code
        == 204
    )
    assert harness.store.objects == {}
    assert harness.client.get(upload["file"]).status_code == 404


def test_only_pdfs_are_accepted(harness: Harness) -> None:
    show_id = _show(harness)
    response = harness.client.post(
        f"/v1/shows/{show_id}/uploads",
        files={"file": ("notes.pdf", b"just text", "application/pdf")},
    )
    assert response.status_code == 415
    assert harness.store.objects == {}


def test_uploads_over_the_limit_are_refused(harness: Harness) -> None:
    show_id = _show(harness)
    too_big = PDF + b"x" * MAX_UPLOAD_BYTES
    response = harness.client.post(
        f"/v1/shows/{show_id}/uploads", files={"file": ("big.pdf", too_big, "application/pdf")}
    )
    assert response.status_code == 413
    assert harness.store.objects == {}


def test_upload_to_an_unknown_show_is_404(harness: Harness) -> None:
    response = harness.client.post(
        f"/v1/shows/{uuid4()}/uploads", files={"file": ("a.pdf", PDF, "application/pdf")}
    )
    assert response.status_code == 404


def test_ready_reports_each_dependency(harness: Harness) -> None:
    body = harness.client.get("/ready").json()
    assert body == {"status": "ready", "checks": {"database": "ok", "queue": "ok"}}

    def broken() -> None:
        raise ConnectionError("connection refused")

    harness.checks["queue"] = broken
    response = harness.client.get("/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not ready"
    assert "connection refused" in response.json()["checks"]["queue"]
