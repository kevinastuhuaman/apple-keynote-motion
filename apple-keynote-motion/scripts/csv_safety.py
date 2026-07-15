#!/usr/bin/env python3
"""Helpers for writing spreadsheet-safe CSV reports."""

from __future__ import annotations

from typing import Any, Mapping


FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def spreadsheet_safe(value: Any) -> Any:
    """Prevent spreadsheet applications from evaluating untrusted text."""
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def spreadsheet_safe_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: spreadsheet_safe(value) for key, value in row.items()}
