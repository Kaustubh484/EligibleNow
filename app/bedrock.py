from __future__ import annotations

import json
import os
from typing import Any

from app.extractor import FIELD_VOCABULARY
from app.models import Operator, PatientFact, Rule, RuleType


JSON_VALUE_SCHEMA: dict[str, Any] = {
    "anyOf": [
        {"type": "string"},
        {"type": "number"},
        {"type": "boolean"},
        {"type": "array", "items": {"type": "string"}},
        {"type": "null"},
    ]
}

FACT_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "enum": sorted(FIELD_VOCABULARY),
                    },
                    "value": JSON_VALUE_SCHEMA,
                    "source_text": {"type": "string"},
                },
                "required": ["field", "value", "source_text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["facts"],
    "additionalProperties": False,
}

RULE_SCHEMA = {
    "type": "object",
    "properties": {
        "rules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rule_id": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": [member.value for member in RuleType],
                    },
                    "field": {
                        "type": "string",
                        "enum": sorted(FIELD_VOCABULARY),
                    },
                    "operator": {
                        "type": "string",
                        "enum": [member.value for member in Operator],
                    },
                    "value": JSON_VALUE_SCHEMA,
                    "source_text": {"type": "string"},
                    "manual_review": {"type": "boolean"},
                },
                "required": [
                    "rule_id",
                    "type",
                    "field",
                    "operator",
                    "value",
                    "source_text",
                    "manual_review",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["rules"],
    "additionalProperties": False,
}


class BedrockOpenAIClient:
    """Small adapter for OpenAI models on Bedrock's Responses-compatible endpoint."""

    def __init__(self, client: Any, model: str) -> None:
        self.client = client
        self.model = model

    @classmethod
    def from_env(cls) -> "BedrockOpenAIClient":
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "Install the Bedrock extra with: pip install -e '.[aws]'"
            ) from exc

        token = os.getenv("AWS_BEARER_TOKEN_BEDROCK")
        model = os.getenv("BEDROCK_MODEL")
        region = os.getenv("AWS_REGION", "us-east-1")
        if not model:
            raise RuntimeError("BEDROCK_MODEL is required")

        if token:
            base_url = os.getenv(
                "BEDROCK_BASE_URL",
                f"https://bedrock-mantle.{region}.api.aws/openai/v1",
            ).rstrip("/")
            client = OpenAI(
                api_key=token,
                base_url=base_url,
                max_retries=0,
            )
        else:
            from openai.providers import bedrock

            client = OpenAI(
                provider=bedrock(
                    region=region,
                    profile=os.getenv("AWS_PROFILE") or None,
                ),
                max_retries=0,
            )
        return cls(client, model)

    def structured(self, *, prompt: str, schema_name: str, schema: dict[str, Any]) -> dict[str, Any]:
        response = self.client.responses.create(
            model=self.model,
            input=prompt,
            text={
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                }
            },
            max_output_tokens=int(os.getenv("BEDROCK_MAX_OUTPUT_TOKENS", "8000")),
            store=False,
        )
        output_text = getattr(response, "output_text", None)
        if not output_text:
            raise RuntimeError("Bedrock response did not contain output_text")
        return json.loads(output_text)


class BedrockFactExtractor:
    def __init__(self, bedrock: BedrockOpenAIClient) -> None:
        self.bedrock = bedrock

    @classmethod
    def from_env(cls) -> "BedrockFactExtractor":
        return cls(BedrockOpenAIClient.from_env())

    def extract(self, note: str) -> list[PatientFact]:
        prompt = f"""Extract patient facts from the de-identified chart note below.
Use only the allowed field vocabulary in the schema. Normalize numeric lab values
to the units implied by each field name. Copy source_text exactly from the note.
Do not infer facts that are not explicitly documented.

CHART NOTE:
{note}"""
        payload = self.bedrock.structured(
            prompt=prompt,
            schema_name="trialcompiler_patient_facts",
            schema=FACT_SCHEMA,
        )
        facts = [PatientFact.model_validate(item) for item in payload["facts"]]
        self._validate_evidence(note, facts)
        return facts

    @staticmethod
    def _validate_evidence(note: str, facts: list[PatientFact]) -> None:
        seen: set[str] = set()
        for fact in facts:
            if fact.field not in FIELD_VOCABULARY:
                raise ValueError(f"Unsupported fact field: {fact.field}")
            if fact.field in seen:
                raise ValueError(f"Duplicate fact field: {fact.field}")
            if fact.source_text.strip() not in note:
                raise ValueError(
                    f"Evidence for {fact.field} is not an exact quote from the note"
                )
            seen.add(fact.field)


class BedrockRuleCompiler:
    def __init__(self, bedrock: BedrockOpenAIClient) -> None:
        self.bedrock = bedrock

    @classmethod
    def from_env(cls) -> "BedrockRuleCompiler":
        return cls(BedrockOpenAIClient.from_env())

    def compile(self, trial_id: str, eligibility_text: str) -> list[Rule]:
        prompt = f"""Compile every distinct eligibility requirement below into rules.
Use only fields and operators from the schema. An exclusion rule describes the
disqualifying condition: when it matches, the evaluator returns fail. Split compound
criteria into separate rules and repeat the same exact source_text quote when needed.
For source_text, copy the complete eligibility criterion line verbatim, including
its number when present; never paraphrase, shorten, or normalize it. Set
manual_review=true only when no allowed field can represent a requirement; do not
mark a rule for manual review merely because its source line contains multiple
requirements. Never drop a criterion.

TRIAL ID: {trial_id}
ELIGIBILITY CRITERIA:
{eligibility_text}"""
        payload = self.bedrock.structured(
            prompt=prompt,
            schema_name="trialcompiler_eligibility_rules",
            schema=RULE_SCHEMA,
        )
        rules = [
            Rule.model_validate({"trial_id": trial_id, **item})
            for item in payload["rules"]
        ]
        for rule in rules:
            if rule.source_text.strip() not in eligibility_text:
                raise ValueError(
                    f"Rule {rule.rule_id} does not preserve an exact source quote"
                )
        return rules
