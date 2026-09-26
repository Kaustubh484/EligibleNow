from fastapi.testclient import TestClient
import pytest

import app.main as main_module
from app.main import app
from app.models import PatientFact


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_refresh_state():
    with main_module.refresh_lock:
        main_module.refresh_state.update(
            {
                "status": "idle",
                "message": "Trial cache is ready.",
                "started_at": None,
                "finished_at": None,
                "last_refreshed_at": None,
            }
        )
    yield


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["trial_count"] == 6
    assert payload["data_source"] == "Synthetic demo"
    assert payload["model"] == "local"
    assert payload["rule_count"] > 0


def test_lists_default_cancer_cohort() -> None:
    response = client.get("/api/cancer-types")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["cancer_type"] == "nsclc"
    assert payload[0]["trial_count"] == 6
    assert payload[0]["rule_count"] > 0
    assert payload[0]["default"] is True


def test_trial_refresh_status_starts_idle() -> None:
    response = client.get("/api/trial-refresh")

    assert response.status_code == 200
    assert response.json()["status"] == "idle"
    assert "last_refreshed_at" in response.json()


def test_trial_refresh_requires_bedrock(monkeypatch) -> None:
    monkeypatch.delenv("BEDROCK_MODEL", raising=False)

    response = client.post("/api/trial-refresh")

    assert response.status_code == 503


def test_trial_refresh_starts_in_background(monkeypatch) -> None:
    monkeypatch.setenv("BEDROCK_MODEL", "test-model")
    monkeypatch.setattr(
        main_module,
        "_start_trial_refresh_thread",
        lambda: None,
    )

    response = client.post("/api/trial-refresh")

    assert response.status_code == 202
    assert response.json()["status"] == "running"


def test_screen_demo_patient() -> None:
    response = client.post("/api/screen", json={"patient_id": "gap-patient"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["cancer_type"] == "nsclc"
    assert payload["total_trial_count"] == 6
    assert payload["screened_trial_count"] == 6
    assert payload["candidate_count"] >= 1
    assert payload["results"][0]["fail_count"] == 0
    assert any(action["field"] == "lvef_pct" for action in payload["actions"])
    assert all(
        criterion["evidence"] or criterion["verdict"] == "unknown"
        for result in payload["results"]
        for criterion in result["criteria"]
    )


def test_guided_answer_resolves_highest_impact_action(monkeypatch) -> None:
    initial = client.post("/api/screen", json={"patient_id": "gap-patient"}).json()
    action = initial["actions"][0]

    class GuidedExtractor:
        def extract(self, evidence: str):
            return [
                PatientFact(
                    field=action["field"],
                    value=60,
                    source_text=evidence,
                )
            ]

    monkeypatch.setattr(main_module, "extractor", GuidedExtractor())
    response = client.post(
        "/api/guided-answer",
        json={
            "cancer_type": initial["cancer_type"],
            "note": initial["patient_note"],
            "facts": initial["facts"],
            "answer": "60 with the protocol-required units",
            "retrieval_limit": initial["screened_trial_count"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["resolved_action"]["field"] == action["field"]
    assert payload["resolved_fact"]["field"] == action["field"]
    assert any(
        fact["field"] == action["field"]
        for fact in payload["screening"]["facts"]
    )
    assert payload["screening"]["patient_note"].endswith(
        f'{action["label"]}: 60 with the protocol-required units'
    )


def test_unknown_patient_is_404() -> None:
    response = client.post("/api/screen", json={"patient_id": "does-not-exist"})

    assert response.status_code == 404


def test_unknown_cancer_cohort_is_404() -> None:
    response = client.post(
        "/api/screen",
        json={
            "cancer_type": "unknown",
            "facts": [
                {
                    "field": "age_years",
                    "value": 50,
                    "source_text": "50-year-old patient",
                }
            ],
        },
    )

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
