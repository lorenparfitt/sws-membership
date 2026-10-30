from fastapi.testclient import TestClient

from sws_membership.main import application


def test_health_reports_ok() -> None:
    response = TestClient(application).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
