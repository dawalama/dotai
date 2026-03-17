"""Shared utilities for dotai."""

import re


def generate_id(name: str) -> str:
    """Generate a URL-friendly ID from a name."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
