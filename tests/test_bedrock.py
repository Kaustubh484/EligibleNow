import pytest

from app.bedrock import BedrockFactExtractor, BedrockRuleCompiler


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


def test_rule_compiler_rejects_duplicate_rule_ids() -> None:
    criterion = "Age 18 years or older."
    rule = {
        "rule_id": "I1",
        "type": "inclusion",
        "field": "age_years",
        "operator": "gte",
        "value": 18,
        "source_text": criterion,
        "manual_review": False,
    }
    compiler = BedrockRuleCompiler(FakeBedrock({"rules": [rule, rule]}))

    with pytest.raises(ValueError, match="duplicate rule IDs"):
        compiler.compile("NCT00000000", criterion)


def test_rule_compiler_grounds_abbreviated_quote_to_unique_criterion() -> None:
    criterion = "1. Participants must be 18 years of age or older."
    compiler = BedrockRuleCompiler(
        FakeBedrock(
            {
                "rules": [
                    {
                        "rule_id": "I1",
                        "type": "inclusion",
                        "field": "age_years",
                        "operator": "gte",
                        "value": 18,
                        "source_text": "Participants must be 18 years or older.",
                        "manual_review": False,
                    }
                ]
            }
        )
    )

    rules = compiler.compile("NCT00000000", criterion)

    assert rules[0].source_text == criterion


def test_rule_compiler_safely_repairs_a_near_exact_unique_quote() -> None:
    criterion = "4. Participants must have an ECOG performance status of 0 or 1."
    compiler = BedrockRuleCompiler(
        FakeBedrock(
            {
                "rules": [
                    {
                        "rule_id": "I4",
                        "type": "inclusion",
                        "field": "ecog",
                        "operator": "in",
                        "value": ["0", "1"],
                        "source_text": (
                            "4. Participants must have ECOG performance "
                            "status of 0 or 1."
                        ),
                        "manual_review": False,
                    }
                ]
            }
        )
    )

    rules = compiler.compile("NCT00000000", criterion)

    assert rules[0].source_text == criterion
