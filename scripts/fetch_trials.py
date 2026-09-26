from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


API_URL = "https://clinicaltrials.gov/api/v2/studies"


def fetch_recruiting_trials(
    condition: str,
    limit: int,
    statuses: str = "RECRUITING|NOT_YET_RECRUITING",
    treatment_only: bool = True,
) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(
        {
            "query.cond": condition,
            "filter.overallStatus": statuses,
            "pageSize": min(max(limit * 5, 50), 100),
            "format": "json",
        }
    )
    request = urllib.request.Request(
        f"{API_URL}?{query}",
        headers={"User-Agent": "TrialCompiler/0.1 (hackathon demo)"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    studies = payload.get("studies", [])
    if treatment_only:
        studies = [study for study in studies if is_treatment_trial(study)]
    return [normalize_study(study) for study in studies[:limit]]


def is_treatment_trial(study: dict[str, Any]) -> bool:
    protocol = study.get("protocolSection", {})
    design = protocol.get("designModule", {})
    interventions = protocol.get("armsInterventionsModule", {}).get(
        "interventions",
        [],
    )
    intervention_types = {
        intervention.get("type")
        for intervention in interventions
    }
    return (
        design.get("studyType") == "INTERVENTIONAL"
        and bool(intervention_types & {"DRUG", "BIOLOGICAL"})
        and bool(
            protocol.get("eligibilityModule", {}).get("eligibilityCriteria")
        )
    )


def normalize_study(study: dict[str, Any]) -> dict[str, Any]:
    protocol = study["protocolSection"]
    identification = protocol.get("identificationModule", {})
    status = protocol.get("statusModule", {})
    design = protocol.get("designModule", {})
    conditions = protocol.get("conditionsModule", {})
    description = protocol.get("descriptionModule", {})
    contacts = protocol.get("contactsLocationsModule", {})
    eligibility = protocol.get("eligibilityModule", {})
    interventions = protocol.get("armsInterventionsModule", {}).get(
        "interventions",
        [],
    )

    locations = []
    for location in contacts.get("locations", []):
        if not location.get("city"):
            continue
        locations.append(
            {
                "facility": location.get("facility", "Study site"),
                "city": location["city"],
                "state": location.get("state", ""),
            }
        )

    phases = design.get("phases") or ["Not applicable"]
    return {
        "trial_id": identification.get("nctId", "UNKNOWN"),
        "title": identification.get("briefTitle", "Untitled study"),
        "phase": " / ".join(phase.replace("_", " ").title() for phase in phases),
        "status": status.get("overallStatus", "Unknown").replace("_", " ").title(),
        "summary": description.get("briefSummary", ""),
        "conditions": conditions.get("conditions", []),
        "study_type": design.get("studyType", "Unknown").replace("_", " ").title(),
        "intervention_types": sorted(
            {
                intervention.get("type", "Unknown").replace("_", " ").title()
                for intervention in interventions
            }
        ),
        "locations": locations[:8],
        "eligibility_text": re.sub(
            r"\\([<>\[\]])",
            r"\1",
            eligibility.get("eligibilityCriteria", ""),
        ),
        "synthetic": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cache recruiting ClinicalTrials.gov studies for TrialCompiler."
    )
    parser.add_argument("--condition", default="non-small cell lung cancer")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--statuses",
        default="RECRUITING|NOT_YET_RECRUITING",
        help="ClinicalTrials.gov overall-status filter.",
    )
    parser.add_argument(
        "--all-study-types",
        action="store_true",
        help="Include observational and non-drug studies.",
    )
    parser.add_argument("--output", type=Path, default=Path("data/raw_trials.json"))
    args = parser.parse_args()

    trials = fetch_recruiting_trials(
        args.condition,
        args.limit,
        args.statuses,
        treatment_only=not args.all_study_types,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(trials, indent=2), encoding="utf-8")
    print(f"Saved {len(trials)} studies to {args.output}")


if __name__ == "__main__":
    main()
