from fastapi.testclient import TestClient

from api import app


client = TestClient(app)


def test_health_endpoint_reports_configuration():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["service"] == "india-invoice-ai-api"
    assert response.json()["max_upload_bytes"] > 0


def test_process_endpoint_uses_existing_workflow():
    response = client.post(
        "/api/process",
        files={"file": ("invoice.txt", b"Invoice Number: API-1\n", "text/plain")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "invoice.txt"
    assert body["invoice"]["invoice_number"] == "API-1"
    assert "source_markdown" not in body


def test_batch_endpoint_isolates_unsupported_files():
    response = client.post(
        "/api/batch",
        files=[
            ("files", ("ok.txt", b"Invoice Number: API-1\n", "text/plain")),
            ("files", ("bad.docx", b"not supported", "application/octet-stream")),
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["failed"] == 1
    assert body["results"][1]["status"] == "processing_failed"


def test_evaluation_endpoint_returns_traceable_reports():
    response = client.get("/api/evaluation")

    assert response.status_code == 200
    assert response.json()["available"] is True