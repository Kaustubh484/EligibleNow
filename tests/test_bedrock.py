import pytest

from app.bedrock import BedrockFactExtractor


class FakeBedrock:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def structured(self, **_: object) -> dict:
        return self.payload


def test_fact_extractor_validates_structured_output() -> None:
    note = "ECOG 1. Creatinine 1.1 mg/dL."
    extractor = BedrockFactExtractor(
        FakeBedrock(
            {
                "facts": [
                    {"field": "ecog", "value": 1, "source_text": "ECOG 1."},
                    {
                        "field": "creatinine_mg_dl",
                        "value": 1.1,
                        "source_text": "Creatinine 1.1 mg/dL.",
                    },
                ]
            }
        )
    )

    facts = extractor.extract(note)

    assert [fact.field for fact in facts] == ["ecog", "creatinine_mg_dl"]


def test_fact_extractor_rejects_invented_evidence() -> None:
    extractor = BedrockFactExtractor(
        FakeBedrock(
            {
                "facts": [
                    {
                        "field": "lvef_pct",
                        "value": 60,
                        "source_text": "LVEF 60%.",
                    }
                ]
            }
        )
    )

    with pytest.raises(ValueError, match="exact quote"):
        extractor.extract("ECOG 1.")


def test_fact_extractor_grounds_abbreviated_quote_to_unique_sentence() -> None:
    note = "EGFR, ALK, and ROS1 negative. ECOG 1."
    extractor = BedrockFactExtractor(
        FakeBedrock(
            {
                "facts": [
                    {
                        "field": "egfr_sensitizing_mutation",
                        "value": False,
                        "source_text": "EGFR negative.",
                    }
                ]
            }
        )
    )

    facts = extractor.extract(note)

    assert facts[0].source_text == "EGFR, ALK, and ROS1 negative."
