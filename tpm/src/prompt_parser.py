"""Parse prompt markdown files into structured query objects.

Each prompt file (e.g. tpmhelloQuery.md) contains one or more numbered
queries with a description and a set of assumptions that together define
a natural-language question to send to the MCP Data Agent.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class QueryBlock:
    """A single query extracted from a prompt markdown file."""

    number: int
    title: str
    description: str
    assumptions: List[str] = field(default_factory=list)

    def to_question(self) -> str:
        """Convert to a natural-language question for the MCP agent.

        Combines the description and all assumptions into a single
        well-formed prompt string.
        """
        parts = [self.description.strip()]
        if self.assumptions:
            parts.append("Constraints: " + "; ".join(
                a.strip().rstrip(".") for a in self.assumptions
            ) + ".")
        return " ".join(parts)


def parse_prompt_file(filepath: Path) -> List[QueryBlock]:
    """Parse a prompt markdown file and return a list of QueryBlocks.

    The parser looks for headings that match the pattern::

        ### Query <N> – <Title>
        or
        ## Query <N> - <Title>

    and then collects the Description and Assumptions sections that follow.

    For files that don't use numbered queries (e.g. attestation, clear,
    statechange), the entire Description block is returned as a single
    QueryBlock.

    Args:
        filepath: Path to the .md prompt file.

    Returns:
        List of QueryBlock objects in document order.
    """
    filepath = Path(filepath)
    text = filepath.read_text(encoding="utf-8")

    # Try numbered query pattern first
    # Matches: ### Query 1 – Title  or  ## Query 1 - Title
    query_heading_re = re.compile(
        r"^#{2,3}\s+Query\s+(\d+)\s*[\u2013\u2014-]\s*(.+)",
        re.MULTILINE,
    )
    matches = list(query_heading_re.finditer(text))

    if matches:
        return _parse_numbered_queries(text, matches)

    # Fallback: single-query files (attestation, clear, statechange)
    return _parse_single_query(text, filepath.stem)


def _parse_numbered_queries(text: str, matches: list) -> List[QueryBlock]:
    """Extract QueryBlocks for files with numbered Query headings."""
    blocks: List[QueryBlock] = []
    for i, match in enumerate(matches):
        number = int(match.group(1))
        title = match.group(2).strip()

        # Section text runs from after the heading to the next heading or EOF
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section = text[start:end]

        description = _extract_section(section, "Description")
        assumptions = _extract_list(section, "Assumptions")

        blocks.append(QueryBlock(
            number=number,
            title=title,
            description=description or title,
            assumptions=assumptions,
        ))
    return blocks


def _parse_single_query(text: str, stem: str) -> List[QueryBlock]:
    """Parse files that have a single Description + Assumptions block."""
    description = _extract_section(text, "Description")
    assumptions = _extract_list(text, "Assumptions")

    return [QueryBlock(
        number=1,
        title=stem,
        description=description or stem,
        assumptions=assumptions,
    )]


def _extract_section(text: str, heading: str) -> str:
    """Extract plain-text content after a 'Heading:' line."""
    pattern = re.compile(
        rf"^{heading}:\s*\n(.*?)(?=\n\S|\n---|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(text)
    if m:
        return m.group(1).strip()
    return ""


def _extract_list(text: str, heading: str) -> List[str]:
    """Extract bullet-list items after a 'Heading:' line."""
    pattern = re.compile(
        rf"^{heading}:\s*\n((?:\s*-\s+.+\n?)+)",
        re.MULTILINE,
    )
    m = pattern.search(text)
    if not m:
        return []
    items = re.findall(r"-\s+(.+)", m.group(1))
    return [item.strip() for item in items]
