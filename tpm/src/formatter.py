"""Format MCP responses for console and file output."""

from datetime import datetime
from pathlib import Path
from typing import List, Tuple


def format_results(
    scenario: str,
    results: List[Tuple[int, str, str]],
) -> str:
    """Format a list of query results into a Markdown report.

    Args:
        scenario: Scenario name (e.g. "hello").
        results: List of (query_number, query_title, response_text) tuples.

    Returns:
        A complete Markdown report string.
    """
    lines: list[str] = []
    lines.append(f"# TPM {scenario.title()} – Orchestrator Report")
    lines.append(f"_Generated: {datetime.now():%Y-%m-%d %H:%M:%S}_\n")

    for number, title, response in results:
        lines.append(f"## Query {number}: {title}\n")
        lines.append(response.strip())
        lines.append("")  # blank line separator

    lines.append("---")
    lines.append("Demo Completed.")
    return "\n".join(lines)


def save_report(content: str, output_dir: Path, scenario: str) -> Path:
    """Write a report to disk and return the file path.

    Args:
        content: Markdown content to write.
        output_dir: Directory to store reports.
        scenario: Scenario name used in the filename.

    Returns:
        Path to the written report file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{scenario}_report_{timestamp}.md"
    path = output_dir / filename
    path.write_text(content, encoding="utf-8")
    return path
