from __future__ import annotations

import argparse

from openai import OpenAI
from openai.providers import bedrock


DEFAULT_MODELS = [
    "openai.gpt-6-luna",
    "openai.gpt-5.6-luna",
    "openai.gpt-5.4",
    "openai.gpt-oss-20b-1:0",
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find an OpenAI Bedrock model that permits inference."
    )
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--profile", default=None)
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    args = parser.parse_args()

    client = OpenAI(
        provider=bedrock(region=args.region, profile=args.profile),
        max_retries=0,
    )
    for model in args.models:
        try:
            response = client.responses.create(
                model=model,
                input="Reply with exactly: ok",
                max_output_tokens=128,
                store=False,
            )
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            print(f"unavailable | {model} | HTTP {status or 'error'}")
            continue
        if response.output_text.strip() == "ok":
            print(f"available   | {model} | {response.status}")
            return
        print(f"unexpected  | {model} | {response.status}")

    raise SystemExit("No probed model permitted inference")


if __name__ == "__main__":
    main()

