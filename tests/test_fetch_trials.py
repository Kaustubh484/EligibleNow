import hashlib

from scripts.fetch_trials import is_treatment_trial, normalize_study


def study(*, study_type: str = "INTERVENTIONAL", intervention_type: str = "DRUG"):
    return {
        "protocolSection": {
            "identificationModule": {
                "nctId": "NCT00000001",
                "briefTitle": "Targeted therapy study",
            },
            "statusModule": {"overallStatus": "RECRUITING"},
            "designModule": {
                "studyType": study_type,
                "phases": ["PHASE2"],
            },
            "conditionsModule": {"conditions": ["Cancer"]},
            "descriptionModule": {"briefSummary": "Summary"},
            "contactsLocationsModule": {"locations": []},
            "eligibilityModule": {
                "eligibilityCriteria": "Participants must be 18 years or older."
            },
            "armsInterventionsModule": {
                "interventions": [
                    {"type": intervention_type, "name": "Examplemab"}
                ]
            },
        }
    }


def test_treatment_filter_requires_interventional_drug_or_biologic() -> None:
    assert is_treatment_trial(study())
    assert is_treatment_trial(study(intervention_type="BIOLOGICAL"))
    assert not is_treatment_trial(study(study_type="OBSERVATIONAL"))
    assert not is_treatment_trial(study(intervention_type="DEVICE"))


def test_normalize_study_preserves_interventions_and_hashes_eligibility() -> None:
    normalized = normalize_study(study())
    eligibility = "Participants must be 18 years or older."

    assert normalized["intervention_names"] == ["Examplemab"]
    assert normalized["eligibility_hash"] == hashlib.sha256(
        eligibility.encode("utf-8")
    ).hexdigest()
