#!/usr/bin/env python3
"""
main.py — CLI entrypoint for the faceless-gen pipeline.

Usage:
    python main.py --prompt "Your topic here" [--job-id abc123]
"""

import argparse
import os
import secrets
import sys

# Load .env before any settings imports
from dotenv import load_dotenv

load_dotenv()

from backend.pipeline.graph import compiled_graph
from backend.pipeline.state import initial_state


def main() -> int:
    parser = argparse.ArgumentParser(
        description="faceless-gen: Generate a faceless video from a text prompt."
    )
    parser.add_argument(
        "--prompt",
        required=True,
        help="Topic or idea for the video.",
    )
    parser.add_argument(
        "--job-id",
        default=None,
        help="Optional job ID (12-char hex). Auto-generated if not provided.",
    )
    args = parser.parse_args()

    job_id = args.job_id or secrets.token_hex(6)
    print(f"Job ID: {job_id}")
    print(f"Prompt: {args.prompt}")
    print()

    state = initial_state(job_id=job_id, user_prompt=args.prompt)
    result = compiled_graph.invoke(state)

    print("\n--- Progress Log ---")
    for entry in result.get("progress_log", []):
        print(f"  {entry}")

    if result.get("error"):
        print(f"\n[ERROR] {result['error']}", file=sys.stderr)
        return 1

    print(f"\n[SUCCESS] Final output: {result.get('final_output')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
