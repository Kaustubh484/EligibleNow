# TrialCompiler

TrialCompiler screens one de-identified patient note against a library of clinical
trial rules. Every criterion returns `pass`, `fail`, or `unknown`, with the exact
source sentence behind the decision. Missing facts are grouped into a practical
coordinator action list.

This repository contains a complete hackathon demo:

- FastAPI API and single-page coordinator UI
- deterministic eligibility evaluator with inclusion and exclusion semantics
- evidence-preserving fact extraction through an OpenAI model on Amazon Bedrock
- three cancer cohorts with up to 100 Recruiting or Not Yet Recruiting treatment
  studies each
- NSCLC, breast cancer, and colorectal cancer screening
- deterministic relevance retrieval before detailed rule evaluation
- six synthetic fallback trials and seven synthetic patient examples
- ranked candidates, hard-fail visibility, and unknowns-to-actions grouping
- unit and API tests

## Run it

Python 3.10 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e '.[dev]'
uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). API documentation is at
[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

## Test it

```bash
pytest
```

## API

`POST /api/screen` accepts one of:

```json
{"patient_id": "gap-patient"}
```

```json
{
  "cancer_type": "nsclc",
  "retrieval_limit": 25,
  "note": "58-year-old woman with stage IV NSCLC. ECOG 1..."
}
```

```json
{
  "facts": [
    {
      "field": "creatinine_mg_dl",
      "value": 1.1,
      "source_text": "Creatinine 1.1 mg/dL"
    }
  ]
}
```

The `/screen` and `/trials/{id}` aliases match the original project plan.
The response reports both `total_trial_count` and `screened_trial_count`, so
retrieval narrowing is explicit rather than hidden. Set `retrieval_limit` to `100`
to evaluate the full cached cohort.

## Safety and data

The patient examples are synthetic. The cohort caches referenced by
`data/cohorts.json` are compiled from the public ClinicalTrials.gov API;
`data/trials.json` remains an offline synthetic fallback. The app is decision
support, not a medical device, and does not determine final enrollment. A qualified
study team must check the current protocol and source record.

The model translates trial prose and de-identified chart text into constrained,
evidence-linked facts and rules. Deterministic Python code makes every
`pass`/`fail`/`unknown` decision. Requirements that cannot be represented safely are
shown as manual review rather than guessed.

## Use OpenAI models on Amazon Bedrock

The optional Bedrock path uses the OpenAI-compatible Responses endpoint and strict
JSON Schema output, following the
[official OpenAI Amazon Bedrock guide](https://developers.openai.com/api/docs/guides/amazon-bedrock).
Install the adapter and provide the model enabled in Workshop Studio:

```bash
python3 -m pip install -e '.[aws]'
export AWS_BEARER_TOKEN_BEDROCK='...'
export AWS_REGION='us-east-1'
export BEDROCK_MODEL='openai.gpt-5.6-luna'
export BEDROCK_MAX_OUTPUT_TOKENS='16000'
export TRIALCOMPILER_EXTRACTOR='bedrock'
export TRIALCOMPILER_COHORTS_FILE='cohorts.json'
uvicorn app.main:app --reload
```

If `AWS_BEARER_TOKEN_BEDROCK` is omitted, the adapter uses the standard AWS
credential chain and SigV4 signing. `BEDROCK_BASE_URL` defaults to
`https://bedrock-mantle.${AWS_REGION}.api.aws/openai/v1` for bearer-token
authentication and can be overridden. The adapter validates the structured response
again in Python and rejects evidence that is not an exact quote from the submitted
note.

Probe the enabled model IDs before a Workshop run:

```bash
python3 -m scripts.check_bedrock --region us-east-1 --profile default
```

## Synchronize the trial cache

Refresh every configured cohort and incrementally compile changed protocols:

```bash
python3 -m scripts.sync_cohorts --workers 3
```

The synchronizer fetches the cohort limits in `data/cohorts.json`, hashes each
eligibility document, reuses unchanged compiled rules, and sends only new or changed
protocols to Bedrock. To refresh registry metadata without invoking Bedrock:

```bash
python3 -m scripts.sync_cohorts --fetch-only
```

To fetch one public recruiting interventional drug or biological cohort manually:

```bash
python3 -m scripts.fetch_trials \
  --condition 'breast cancer' \
  --limit 100 \
  --output data/raw_trials.breast.json
```

The default status filter is `RECRUITING|NOT_YET_RECRUITING`. Observational,
behavioral, device-only, closed, and active-but-not-recruiting studies are excluded.
Pass `--all-study-types` to disable the treatment-study filter.

Compile every eligibility criterion into cached rules with the configured Bedrock
model:

```bash
python3 -m scripts.compile_trials \
  --input data/raw_trials.breast.json \
  --output data/trials.breast.json \
  --resume \
  --workers 3
```

Point the app at that cache:

```bash
export TRIALCOMPILER_COHORTS_FILE='cohorts.json'
export TRIALCOMPILER_EXTRACTOR='bedrock'
uvicorn app.main:app --reload
```
