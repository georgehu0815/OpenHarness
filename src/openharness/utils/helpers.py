"""Shared utility helpers for channel implementations."""

from __future__ import annotations

import re
from pathlib import Path


def split_message(text: str, max_len: int) -> list[str]:
    """Split *text* into chunks of at most *max_len* characters.

    Splits prefer paragraph breaks, then newlines, then word boundaries so that
    the output reads naturally when each chunk is sent as a separate message.
    """
    if not text:
        return []
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break

        slice_ = text[:max_len]

        # Prefer splitting on a blank line (paragraph break)
        pos = slice_.rfind("\n\n")
        if pos > max_len // 2:
            chunks.append(text[: pos + 2].rstrip())
            text = text[pos + 2 :]
            continue

        # Fall back to a single newline
        pos = slice_.rfind("\n")
        if pos > max_len // 2:
            chunks.append(text[:pos].rstrip())
            text = text[pos + 1 :]
            continue

        # Fall back to the last word boundary
        pos = slice_.rfind(" ")
        if pos > max_len // 2:
            chunks.append(text[:pos])
            text = text[pos + 1 :]
            continue

        # Hard cut — no natural break found
        chunks.append(text[:max_len])
        text = text[max_len:]

    return [c for c in chunks if c]


def safe_filename(name: str) -> str:
    """Return a filesystem-safe version of *name*.

    Strips or replaces characters that are invalid on common filesystems.
    Returns an empty string if nothing safe remains.
    """
    if not name:
        return ""
    # Replace path separators and NUL bytes
    name = name.replace("/", "_").replace("\\", "_").replace("\x00", "")
    # Remove characters disallowed on Windows/macOS/Linux
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "", name)
    # Collapse multiple underscores/spaces
    name = re.sub(r"_{2,}", "_", name).strip("_").strip()
    return name


def get_data_path() -> Path:
    """Return the OpenHarness user data directory (~/.openharness)."""
    path = Path.home() / ".openharness"
    path.mkdir(parents=True, exist_ok=True)
    return path
