from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["trial_count"] == 6
    assert payload["data_source"] == "Synthetic demo"
    assert payload["model"] == "local"
    assert payload["rule_count"] > 0


def test_screen_demo_patient() -> None:
    response = client.post("/api/screen", json={"patient_id": "gap-patient"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["candidate_count"] >= 1
    assert payload["results"][0]["fail_count"] == 0
    assert any(action["field"] == "lvef_pct" for action in payload["actions"])
    assert all(
        criterion["evidence"] or criterion["verdict"] == "unknown"
        for result in payload["results"]
        for criterion in result["criteria"]
    )


def test_unknown_patient_is_404() -> None:
    response = client.post("/api/screen", json={"patient_id": "does-not-exist"})

    assert response.status_code == 404


def test_model_extraction_failure_returns_clean_error(monkeypatch) -> None:
    class FailingExtractor:
        def extract(self, _: str):
            raise ValueError("raw provider failure")

    monkeypatch.setattr(main_module, "extractor", FailingExtractor())

    response = client.post(
        "/api/screen",
        json={"note": "A sufficiently long de-identified patient note."},
    )

    assert response.status_code == 502
    assert response.json()["detail"].startswith(
        "The model could not produce evidence-grounded patient facts"
    )
    assert "provider" not in response.text
