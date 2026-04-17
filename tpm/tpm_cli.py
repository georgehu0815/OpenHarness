#!/usr/bin/env python3
"""tpm — Unified TPM Data Agent CLI

Subcommands
-----------
Scenario runners (call Fabric Data Agent MCP and return results):
  hello        Hello scenario: success rate, top errors, top failing models
  attestation  Attestation status: distribution + top 3 cannot-be-attested
  clear        TPM clear reasons: top 3 reasons + top 3 manufacturers
  rqv          RQV measure failure analysis (3-query deep dive)
  statechange  State changes: firmware, manufacturer, device model shifts

Utilities:
  decode       Decode numeric TPM Manufacturer IDs to vendor names
  scenarios    List all available scenarios and their query descriptions

Usage examples
--------------
  tpm hello
  tpm attestation --save-report
  tpm statechange --dry-run
  tpm rqv -v
  tpm decode 1229346816 1297303124 1229870147
  tpm decode --json 1229346816
  tpm decode --table
  tpm scenarios
"""

import argparse
import json
import logging
import struct
import sys
from pathlib import Path

# ── Ensure project src is importable regardless of CWD ────────────────────────
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

# ── Scenario → prompt file mapping (mirrors orchestrator.py) ──────────────────
SCENARIOS: dict[str, dict] = {
    "hello": {
        "file": "tpmhelloQuery.md",
        "description": "Success rate, top 5 errors, top 5 failing OEM models (last 7 days)",
    },
    "attestation": {
        "file": "tpmattestationstatusQuery.md",
        "description": "Device distribution by HealthStatus + top 3 cannot-be-attested manufacturers",
    },
    "clear": {
        "file": "tpmclearQuery.md",
        "description": "Top 3 TPM clear reasons + top 3 manufacturers showing clears",
    },
    "rqv": {
        "file": "tpmrqvQuery.md",
        "description": "RQV measure failure analysis: failing slice, patterns, missing attributes",
    },
    "statechange": {
        "file": "tpmstatechangeQuery.md",
        "description": "Firmware changes, manufacturer changes, combined changes — top 3 per category",
    },
}

# ── Vendor table (TCG-registered) ─────────────────────────────────────────────
KNOWN_VENDORS: dict[str, str] = {
    "AMD ": "AMD",
    "ATML": "Atmel",
    "BRCM": "Broadcom",
    "CSCO": "Cisco",
    "FLYS": "Flyslice Technologies",
    "GNMD": "Goldenmars Technology",
    "HPE ": "HP Enterprise",
    "HISI": "HiSilicon",
    "IBM ": "IBM",
    "IFX ": "Infineon Technologies",
    "INTC": "Intel",
    "LEN ": "Lenovo",
    "MSFT": "Microsoft",
    "NSM ": "National Semiconductor",
    "NTC ": "Nuvoton Technology",
    "NTZ ": "Nationz Technologies",
    "NVDA": "NVIDIA",
    "QCOM": "Qualcomm",
    "ROCC": "Fuzhou Rockchip",
    "SMSC": "SMSC",
    "SNS ": "Sinosun Technology",
    "STM ": "ST Microelectronics",
    "TXN ": "Texas Instruments",
    "WEC ": "Winbond Electronics",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def decode_manufacturer_id(mid: int) -> tuple[str, str]:
    """Return (ascii_code, vendor_name) for a numeric manufacturer ID."""
    try:
        raw = struct.pack(">I", mid)
        code = raw.decode("ascii", errors="replace").rstrip("\x00")
    except struct.error:
        return ("?", "invalid ID")
    vendor = KNOWN_VENDORS.get(code.ljust(4)) or KNOWN_VENDORS.get(code) or "Unknown"
    return code, vendor


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
    )


# ── Subcommand handlers ───────────────────────────────────────────────────────

def cmd_scenarios(args: argparse.Namespace) -> int:
    """List all available scenarios."""
    print(f"\n{'Scenario':<14}  Description")
    print("-" * 72)
    for name, meta in SCENARIOS.items():
        print(f"  {name:<12}  {meta['description']}")
    print()
    return 0


def cmd_decode(args: argparse.Namespace) -> int:
    """Decode numeric manufacturer IDs to vendor names."""
    ids: list[int] = args.ids

    # Read from stdin if no ids provided and stdin has data
    if not ids and not sys.stdin.isatty():
        ids = [int(x) for line in sys.stdin for x in line.split() if x.strip()]

    if not ids:
        print("Usage: tpm decode <id> [<id2> ...]  |  tpm decode --table")
        return 1

    if args.json_out:
        results = [
            {"id": mid, "code": code, "vendor": vendor}
            for mid in ids
            for code, vendor in [decode_manufacturer_id(mid)]
        ]
        print(json.dumps(results, indent=2))
        return 0

    print(f"\n{'ID':>12}  {'Code':<6}  Vendor")
    print("-" * 38)
    for mid in ids:
        code, vendor = decode_manufacturer_id(mid)
        print(f"{mid:>12}  {code:<6}  {vendor}")
    print()
    return 0


def cmd_decode_table(args: argparse.Namespace) -> int:
    """Print the full known-vendor table."""
    print(f"\n{'Code':<6}  Vendor")
    print("-" * 30)
    for code, name in sorted(KNOWN_VENDORS.items()):
        print(f"{code.strip():<6}  {name}")
    print()
    return 0


def cmd_run_scenario(args: argparse.Namespace) -> int:
    """Run a named TPM scenario against the Fabric Data Agent MCP."""
    _setup_logging(getattr(args, "verbose", False))
    logger = logging.getLogger("tpm")

    scenario = args.scenario
    prompts_dir = _HERE / "prompts"
    prompt_file = prompts_dir / SCENARIOS[scenario]["file"]

    if not prompt_file.exists():
        logger.error("Prompt file not found: %s", prompt_file)
        return 1

    from src.prompt_parser import parse_prompt_file
    from src.config import load_mcp_config
    from src.mcp_client import MCPClient
    from src.formatter import format_results, save_report

    logger.info("Parsing prompt file: %s", prompt_file.name)
    queries = parse_prompt_file(prompt_file)
    logger.info("Found %d query block(s).", len(queries))

    if getattr(args, "dry_run", False):
        print(f"\n=== Dry Run – {scenario.upper()} ===\n")
        for q in queries:
            print(f"  Query {q.number}: {q.title}")
            print(f"    {q.to_question()}\n")
        return 0

    config = load_mcp_config()
    client = MCPClient(config, token=getattr(args, "token", None))

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

    report = format_results(scenario, results)
    print(report)

    if getattr(args, "save_report", False):
        reports_dir = _HERE / "reports"
        path = save_report(report, reports_dir, scenario)
        logger.info("Report saved to %s", path)

    return 0


# ── Argument parser ───────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tpm",
        description="TPM Data Agent CLI — run queries against Fabric and decode TPM data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # ── scenarios ──
    sub.add_parser("scenarios", help="List all available scenarios")

    # ── decode ──
    p_decode = sub.add_parser("decode", help="Decode numeric TPM manufacturer IDs to vendor names")
    p_decode.add_argument("ids", nargs="*", type=int, metavar="ID", help="Numeric manufacturer IDs")
    p_decode.add_argument("--json", dest="json_out", action="store_true", help="Output as JSON")
    p_decode.add_argument("--table", action="store_true", help="Print the full vendor table")

    # ── scenario subcommands ──
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dry-run", action="store_true", help="Print queries without calling MCP")
    common.add_argument("--save-report", action="store_true", help="Save report to reports/")
    common.add_argument("--token", default=None, help="Bearer token (skips DefaultAzureCredential)")
    common.add_argument("--verbose", "-v", action="store_true", help="Debug logging")

    for name, meta in SCENARIOS.items():
        sub.add_parser(name, parents=[common], help=meta["description"])

    return parser


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "scenarios":
        sys.exit(cmd_scenarios(args))

    if args.command == "decode":
        if getattr(args, "table", False):
            sys.exit(cmd_decode_table(args))
        sys.exit(cmd_decode(args))

    # All other commands are scenario runners
    args.scenario = args.command
    sys.exit(cmd_run_scenario(args))


if __name__ == "__main__":
    main()
