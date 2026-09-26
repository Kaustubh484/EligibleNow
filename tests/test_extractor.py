from app.extractor import DemoFactExtractor


def fact_map(note: str) -> dict[str, object]:
    return {fact.field: fact.value for fact in DemoFactExtractor().extract(note)}


def test_extracts_worked_example() -> None:
    facts = fact_map(
        "58-year-old woman with stage IV non-small cell lung cancer, "
        "adenocarcinoma. EGFR negative. ECOG 1. Creatinine 1.1 mg/dL. "
        "No prior systemic therapy."
    )

    assert facts["age_years"] == 58
    assert facts["sex"] == "female"
    assert facts["diagnosis"] == "NSCLC"
    assert facts["stage"] == "IV"
    assert facts["histology"] == "adenocarcinoma"
    assert facts["ecog"] == 1
    assert facts["creatinine_mg_dl"] == 1.1
    assert facts["prior_systemic_therapy"] is False
    assert facts["biomarkers"] == []


def test_extracts_present_and_absent_brain_metastases() -> None:
    extractor = DemoFactExtractor()

    absent = {fact.field: fact.value for fact in extractor.extract("No active brain metastases.")}
    present = {
        fact.field: fact.value
        for fact in extractor.extract("Active brain metastases are present.")
    }

    assert absent["brain_mets_active"] is False
    assert present["brain_mets_active"] is True

