#!/usr/bin/env python3
"""Helpers for writing spreadsheet-safe CSV reports."""

from __future__ import annotations

import unicodedata
from typing import Any, Mapping


FORMULA_PREFIXES = ("=", "+", "-", "@")


def formula_candidate(value: str) -> str:
    index = 0
    while index < len(value):
        character = value[index]
        if not character.isspace() and unicodedata.category(character) != "Cc":
            break
        index += 1
    return value[index:]


def spreadsheet_safe(value: Any) -> Any:
    """Prevent spreadsheet applications from evaluating untrusted text."""
    if isinstance(value, str) and formula_candidate(value).startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def spreadsheet_safe_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: spreadsheet_safe(value) for key, value in row.items()}
