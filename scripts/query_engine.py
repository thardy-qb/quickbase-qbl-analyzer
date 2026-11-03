"""Filter and project parsed QBL collections without loading results into chat.

The full parsed inventory can be many times the size of the source QBL, so it is
loaded here inside the analyzer process. Only the filtered projection is printed,
which keeps the caller's working set proportional to the answer rather than to
the solution.
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Operators are ordered longest-first so that ">=" is matched before ">".
OPERATORS: Tuple[Tuple[str, str], ...] = (
    ("!~", "not_contains"),
    ("!=", "ne"),
    (">=", "gte"),
    ("<=", "lte"),
    ("=~", "contains"),
    ("=", "eq"),
    (">", "gt"),
    ("<", "lt"),
)

MAX_CELL_WIDTH = 400


class QueryError(ValueError):
    """Raised for malformed filters, unknown collections, or unknown columns."""


def load_inventory(source: Path) -> Dict[str, Any]:
    """Load `parsed-qbl.json` from a file path or an output directory."""
    path = Path(source).expanduser().resolve()
    if path.is_dir():
        candidate = path / "parsed-qbl.json"
        if not candidate.is_file():
            raise QueryError(f"No parsed-qbl.json found in {path}")
        path = candidate
    if not path.is_file():
        raise QueryError(f"Inventory file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise QueryError("parsed-qbl.json must contain a JSON object.")
    return payload


def collections_of(payload: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Return only the list-of-row collections from a parsed inventory."""
    parsed = payload.get("parsed_data", payload)
    if not isinstance(parsed, dict):
        raise QueryError("parsed-qbl.json is missing a 'parsed_data' object.")
    return {
        name: [row for row in rows if isinstance(row, dict)]
        for name, rows in parsed.items()
        if isinstance(rows, list)
    }


def column_names(rows: Sequence[Dict[str, Any]]) -> List[str]:
    """Return column names in first-seen order across all rows."""
    seen: Dict[str, None] = {}
    for row in rows:
        for key in row:
            seen.setdefault(str(key), None)
    return list(seen)


def parse_filter(expression: str) -> Tuple[str, str, str]:
    """Split a `column<op>value` filter into its parts."""
    for token, op in OPERATORS:
        index = expression.find(token)
        if index > 0:
            column = expression[:index].strip()
            value = expression[index + len(token):].strip()
            if column:
                return column, op, value
    raise QueryError(
        f"Could not parse filter {expression!r}. "
        "Use column=value, column!=value, column=~substring, column!~substring, "
        "or a numeric comparison with >, <, >=, <=."
    )


def resolve_column(requested: str, available: Sequence[str]) -> str:
    """Match a column name case-insensitively, ignoring surrounding whitespace."""
    wanted = requested.strip().casefold()
    for name in available:
        if name.strip().casefold() == wanted:
            return name
    raise QueryError(
        f"Unknown column {requested!r}. Available columns: {', '.join(available)}"
    )


def _as_number(value: Any) -> Optional[float]:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def matches(row: Dict[str, Any], column: str, op: str, value: str) -> bool:
    cell = row.get(column, "")
    cell_text = "" if cell is None else str(cell)

    if op in ("eq", "ne"):
        # A blank target matches empty cells and the parser's "N/A" placeholder.
        if value == "":
            is_blank = cell_text.strip() in ("", "N/A")
            return is_blank if op == "eq" else not is_blank
        equal = cell_text.strip().casefold() == value.casefold()
        return equal if op == "eq" else not equal
    if op == "contains":
        return value.casefold() in cell_text.casefold()
    if op == "not_contains":
        return value.casefold() not in cell_text.casefold()

    left, right = _as_number(cell_text), _as_number(value)
    if left is None or right is None:
        return False
    if op == "gt":
        return left > right
    if op == "lt":
        return left < right
    if op == "gte":
        return left >= right
    if op == "lte":
        return left <= right
    raise QueryError(f"Unsupported operator: {op}")


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return str(value)


def run_query(
    payload: Dict[str, Any],
    collection: str,
    *,
    filters: Iterable[str] = (),
    columns: Optional[Sequence[str]] = None,
    limit: Optional[int] = None,
    distinct: bool = False,
    count_only: bool = False,
) -> Dict[str, Any]:
    """Filter one collection and project the requested columns."""
    available = collections_of(payload)
    if collection not in available:
        raise QueryError(
            f"Unknown collection {collection!r}. "
            f"Available: {', '.join(sorted(available))}"
        )

    rows = available[collection]
    all_columns = column_names(rows)

    for expression in filters:
        column, op, value = parse_filter(expression)
        resolved = resolve_column(column, all_columns)
        rows = [row for row in rows if matches(row, resolved, op, value)]

    total_matched = len(rows)

    if columns:
        selected = [resolve_column(c, all_columns) for c in columns]
    else:
        selected = all_columns

    projected = [
        {name: _cell_text(row.get(name, "")) for name in selected} for row in rows
    ]

    if distinct:
        deduped: List[Dict[str, str]] = []
        seen = set()
        for row in projected:
            key = tuple(row.items())
            if key not in seen:
                seen.add(key)
                deduped.append(row)
        projected = deduped

    distinct_count = len(projected)
    truncated = False
    if limit is not None and limit >= 0 and len(projected) > limit:
        projected = projected[:limit]
        truncated = True

    return {
        "collection": collection,
        "total_rows": len(available[collection]),
        "matched_rows": total_matched,
        "returned_rows": len(projected),
        "distinct_rows": distinct_count if distinct else None,
        "truncated": truncated,
        "count_only": count_only,
        "columns": selected,
        "rows": [] if count_only else projected,
    }


def format_table(result: Dict[str, Any]) -> str:
    """Render a query result as an aligned text table."""
    columns = result["columns"]
    rows = result["rows"]

    if result.get("count_only"):
        parts = [
            f"'{result['collection']}': {result['matched_rows']} of "
            f"{result['total_rows']} row(s) matched"
        ]
        if result.get("distinct_rows") is not None:
            parts.append(f"{result['distinct_rows']} distinct")
        return "; ".join(parts)

    if not rows:
        return (
            f"No rows matched in '{result['collection']}' "
            f"({result['total_rows']} row(s) in the collection)."
        )

    widths = {
        c: min(MAX_CELL_WIDTH, max(len(c), *(len(r.get(c, "")) for r in rows)))
        for c in columns
    }
    lines = [
        " | ".join(c.ljust(widths[c]) for c in columns),
        "-+-".join("-" * widths[c] for c in columns),
    ]
    for row in rows:
        cells = []
        for c in columns:
            text = row.get(c, "")
            if len(text) > MAX_CELL_WIDTH:
                text = text[: MAX_CELL_WIDTH - 3] + "..."
            cells.append(text.ljust(widths[c]))
        lines.append(" | ".join(cells))

    footer = (
        f"\n{result['returned_rows']} row(s) shown; "
        f"{result['matched_rows']} matched of {result['total_rows']} in '{result['collection']}'"
    )
    if result["truncated"]:
        footer += " -- output was capped by --limit; raise it or add filters to see the rest"
    return "\n".join(lines) + footer


def format_csv(result: Dict[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=result["columns"], extrasaction="ignore")
    writer.writeheader()
    for row in result["rows"]:
        writer.writerow(row)
    return buffer.getvalue().rstrip("\n")


def format_result(result: Dict[str, Any], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(result, ensure_ascii=False, indent=2)
    if output_format == "csv":
        return format_csv(result)
    return format_table(result)


def describe_collections(payload: Dict[str, Any], descriptions: Dict[str, str]) -> str:
    """List collections with row counts and column names."""
    available = collections_of(payload)
    named = [(n, r) for n, r in available.items() if r]
    empty = sorted(n for n, r in available.items() if not r)

    lines = [
        f"Solution: {payload.get('label', '(unlabeled)')}    QBL version: {payload.get('qbl_version', '?')}",
        "",
        f"{len(named)} populated collection(s):",
        "",
    ]
    for name, rows in sorted(named, key=lambda item: item[0]):
        lines.append(f"{name}  ({len(rows)} rows)")
        if descriptions.get(name):
            lines.append(f"   {descriptions[name]}")
        lines.append(f"   columns: {', '.join(column_names(rows))}")
        lines.append("")
    if empty:
        lines.append(f"Empty collections: {', '.join(empty)}")
    return "\n".join(lines).rstrip("\n")
