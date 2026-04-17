"""TPM Data Agent Orchestrator – CLI entry point.

Run predefined TPM prompt queries against the Fabric Data Agent MCP
server from the command line.

Usage examples::

    # Run all Hello queries
    python -m src.orchestrator --scenario hello

    # Run attestation queries and save report to disk
    python -m src.orchestrator --scenario attestation --save-report

    # Use a custom bearer token instead of DefaultAzureCredential
    python -m src.orchestrator --scenario hello --token <JWT>

    # Dry-run: show the questions that would be sent without calling MCP
    python -m src.orchestrator --scenario hello --dry-run
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict

from .config import load_mcp_config
from .prompt_parser import parse_prompt_file
from .mcp_client import MCPClient
from .formatter import format_results, save_report

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = PROJECT_ROOT / "prompts"

# Mapping of scenario names to prompt files
SCENARIOS: Dict[str, str] = {
    "hello": "tpmhelloQuery.md",
    "attestation": "tpmattestationstatusQuery.md",
    "clear": "tpmclearQuery.md",
    "rqv": "tpmrqvQuery.md",
    "statechange": "tpmstatechangeQuery.md",
}


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="tpm-orchestrator",
        description="Run TPM prompt queries against the Fabric Data Agent MCP server.",
    )
    parser.add_argument(
        "--scenario",
        choices=list(SCENARIOS.keys()),
        default="hello",
        help="Which scenario to run (default: hello).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the questions that would be sent without calling the MCP server.",
    )
    parser.add_argument(
        "--save-report",
        action="store_true",
        help="Save the formatted report to the reports/ directory.",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Bearer token for Fabric API auth (skips DefaultAzureCredential).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose / debug logging.",
    )
    return parser


def run(args: argparse.Namespace) -> int:
    """Execute the orchestrator with the given CLI arguments.

    Returns:
        Exit code (0 = success).
    """
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
    )
    logger = logging.getLogger("orchestrator")

    scenario = args.scenario
    prompt_file = PROMPTS_DIR / SCENARIOS[scenario]

    if not prompt_file.exists():
        logger.error("Prompt file not found: %s", prompt_file)
        return 1

    # ---- Parse queries ----
    logger.info("Parsing prompt file: %s", prompt_file.name)
    queries = parse_prompt_file(prompt_file)
    logger.info("Found %d query block(s).", len(queries))

    if args.dry_run:
        print(f"\n=== Dry Run – {scenario.upper()} ===\n")
        for q in queries:
            print(f"  Query {q.number}: {q.title}")
            print(f"    Question: {q.to_question()}\n")
        return 0

    # ---- Call MCP ----
    config = load_mcp_config()
    client = MCPClient(config, token=args.token)

    results = []
    for q in queries:
        question = q.to_question()
        logger.info("Sending Query %d: %s", q.number, q.title)
        try:
            response = client.ask(question)
        except Exception as exc:
            logger.error("Query %d failed: %s", q.number, exc)
            response = f"_Error: {exc}_"
        results.append((q.number, q.title, response))

    # ---- Format output ----
    report = format_results(scenario, results)
    print(report)

    if args.save_report:
        reports_dir = PROJECT_ROOT / "reports"
        path = save_report(report, reports_dir, scenario)
        logger.info("Report saved to %s", path)

    return 0


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    main()
