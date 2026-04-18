"""Output helpers: JSON (machine) and Rich (human)."""

from __future__ import annotations

import json
import sys
from typing import Any

from rich.console import Console
from rich.table import Table


def print_json(data: Any) -> None:
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def print_pretty(data: Any, title: str | None = None) -> None:
    console = Console()
    if isinstance(data, dict):
        table = Table(title=title, show_header=True, header_style="bold")
        table.add_column("Field")
        table.add_column("Value", overflow="fold")
        for key, value in _flatten(data).items():
            table.add_row(key, _stringify(value))
        console.print(table)
        return
    if isinstance(data, list):
        if not data:
            console.print("[dim](empty)[/dim]")
            return
        if all(isinstance(row, dict) for row in data):
            columns = _union_keys(data)
            table = Table(title=title, show_header=True, header_style="bold")
            for col in columns:
                table.add_column(col, overflow="fold")
            for row in data:
                table.add_row(*[_stringify(row.get(col)) for col in columns])
            console.print(table)
            return
    console.print_json(data=data)


def _flatten(obj: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in obj.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten(value, full_key))
        else:
            flat[full_key] = value
    return flat


def _union_keys(rows: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for row in rows:
        for key in row:
            if key not in seen:
                seen.append(key)
    return seen


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)
