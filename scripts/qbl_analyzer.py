#!/usr/bin/env python3
"""File-only Quickbase QBL solution analysis and query CLI."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
VENDOR_DIR = SCRIPT_DIR / "vendor"

# The `qblparser` package sits beside this script. PyYAML and XlsxWriter are
# bundled as pure-Python trees under `vendor/`, so there is nothing to install.
if VENDOR_DIR.is_dir():
    sys.path.insert(0, str(VENDOR_DIR))
else:
    raise RuntimeError("Bundled Python dependencies are missing.")
sys.path.insert(0, str(SCRIPT_DIR))

from qblparser import (  # noqa: E402
    ENTITY_DESCRIPTIONS,
    detect_qbl_version,
    load_qbl_file,
    load_table_schema_file,
)
from qblparser.entities.relationships import distinct_relationships  # noqa: E402

from digest_writer import write_digest  # noqa: E402
from query_engine import (  # noqa: E402
    QueryError,
    describe_collections,
    format_result,
    load_inventory,
    run_query,
)
from workbook_writer import generate_solution_workbook  # noqa: E402

# Parsing expands a QBL export by roughly 150-200x in peak memory: it builds the
# full entity inventory, cross-reference matrices, and usage analysis in RAM. A
# 1.6 MB synthetic export peaks at about 255 MB. 32 MB is the largest input that stays
# inside a few GB; a larger file is refused with a clear error rather than
# exhausting memory.
MAX_INPUT_BYTES = 32 * 1024 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze and query a Quickbase QBL export using only local files."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    summary = subparsers.add_parser(
        "summary",
        help="Parse a QBL export into a queryable inventory, a digest, and a workbook.",
    )
    summary.add_argument("qbl_file", type=Path)
    summary.add_argument("--table-schema", type=Path, default=None)
    summary.add_argument("--output-dir", type=Path, required=True)
    summary.add_argument("--label", default="")

    collections = subparsers.add_parser(
        "collections",
        help="List collections, row counts, and column names in a parsed inventory.",
    )
    collections.add_argument(
        "inventory",
        type=Path,
        help="Path to parsed-qbl.json, or the output directory that contains it.",
    )

    query = subparsers.add_parser(
        "query",
        help="Filter and project one collection. Only matching rows are printed.",
        epilog=(
            "Filters: col=value, col!=value, col=~substring, col!~substring, "
            "col>N, col<N, col>=N, col<=N. Use col= to match blank cells. "
            "Repeat --where to AND conditions together."
        ),
    )
    query.add_argument(
        "inventory",
        type=Path,
        help="Path to parsed-qbl.json, or the output directory that contains it.",
    )
    query.add_argument("collection", help="Collection name, e.g. fields or pipeline_steps.")
    query.add_argument(
        "--where",
        action="append",
        default=[],
        metavar="EXPR",
        help="Filter expression; repeat to AND conditions.",
    )
    query.add_argument(
        "--columns",
        default="",
        help="Comma-separated columns to return. Defaults to every column.",
    )
    query.add_argument("--limit", type=int, default=50, help="Max rows to print (default 50; -1 for all).")
    query.add_argument("--distinct", action="store_true", help="Drop duplicate projected rows.")
    query.add_argument("--count", action="store_true", help="Print counts only, no rows.")
    query.add_argument(
        "--format",
        dest="output_format",
        choices=("table", "json", "csv"),
        default="table",
    )

    return parser.parse_args()


def validate_input(path: Optional[Path], label: str) -> Optional[Path]:
    if path is None:
        return None
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"{label} not found: {resolved}")
    size = resolved.stat().st_size
    if size > MAX_INPUT_BYTES:
        raise ValueError(
            f"{label} is {size:,} bytes, exceeding the {MAX_INPUT_BYTES:,}-byte limit. "
            "Parsing needs roughly 150-200x the input size in memory, so a larger "
            "export risks exhausting RAM. Split the solution or raise "
            "MAX_INPUT_BYTES if you have the headroom."
        )
    return resolved


def prepare_output_dir(path: Path) -> Path:
    """Create an isolated output directory and remove stale prior-run artifacts."""
    output_dir = path.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    for child in output_dir.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    return output_dir


def load_optional_schema(path: Optional[Path]) -> Any:
    return load_table_schema_file(path) if path else []


def plain(value: Any) -> Any:
    if isinstance(value, defaultdict):
        value = dict(value)
    if isinstance(value, dict):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [plain(item) for item in value]
    return value


def json_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return str(value)


def ordered_headers(rows: Iterable[Dict[str, Any]]) -> List[str]:
    headers: List[str] = []
    seen = set()
    for row in rows:
        for key in row:
            key_text = str(key)
            if key_text not in seen:
                seen.add(key_text)
                headers.append(key_text)
    return headers


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    headers = ordered_headers(rows)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({header: json_cell(row.get(header)) for header in headers})


def write_collection_csvs(output_dir: Path, parsed_data: Dict[str, Any]) -> List[str]:
    csv_dir = output_dir / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    paths: List[str] = []
    for name, rows in parsed_data.items():
        dict_rows = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
        if not dict_rows:
            continue
        path = csv_dir / f"{name}.csv"
        write_csv(path, dict_rows)
        paths.append(str(path))
    return paths


def build_zip(output_dir: Path, zip_name: str) -> Path:
    bundle_path = output_dir / zip_name
    if bundle_path.exists():
        bundle_path.unlink()
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output_dir.rglob("*")):
            if path.is_file() and path != bundle_path:
                archive.write(path, path.relative_to(output_dir))
    return bundle_path


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(plain(payload), indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def solution_counts(parsed_data: Dict[str, Any]) -> Dict[str, int]:
    return {
        key: len(value)
        for key, value in parsed_data.items()
        if isinstance(value, list)
    }


def issue_breakdown(issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Split validation findings by severity and by the layer that found them.

    A single total is not actionable once five layers are running. An error
    blocks a deployment; a warning is pre-existing debt, such as a `!BadRef`
    Quickbase itself wrote when the solution was exported, and reporting the
    two as one number makes a healthy app look broken.
    """
    by_severity: Dict[str, int] = defaultdict(int)
    by_layer: Dict[str, int] = defaultdict(int)
    by_code: Dict[str, Dict[str, Any]] = {}

    for issue in issues:
        if not isinstance(issue, dict):
            continue
        severity = str(issue.get("Severity", "") or "error").lower()
        layer = str(issue.get("Layer", "") or "Other")
        code = str(issue.get("Code", "") or "")
        by_severity[severity] += 1
        by_layer[layer] += 1
        entry = by_code.setdefault(
            code,
            {
                "count": 0,
                "severity": severity,
                "layer": layer,
                "problem": str(issue.get("Problem", "")),
                "remediation": str(issue.get("Remediation", "")),
            },
        )
        entry["count"] += 1

    return {
        "errors": by_severity.get("error", 0),
        "warnings": by_severity.get("warning", 0),
        "by_severity": dict(by_severity),
        "by_layer": dict(by_layer),
        "by_code": by_code,
    }


def render_validation_section(breakdown: Dict[str, Any]) -> List[str]:
    """Render the validation findings as a table of distinct codes.

    Grouped by code rather than listed one per occurrence: five hundred
    findings are usually a dozen distinct problems repeated, and the fix is per
    code, not per occurrence. Every occurrence, with its path, is still in the
    workbook and in `parsed-qbl.json`.
    """
    by_code = breakdown.get("by_code") or {}
    if not by_code:
        return []

    lines = [
        "",
        "## Validation Findings",
        "",
        "| Code | Layer | Severity | Count | Example | Fix |",
        "|---|---|---|---:|---|---|",
    ]
    ordered = sorted(
        by_code.items(),
        key=lambda item: (
            0 if item[1]["severity"] == "error" else 1,
            -item[1]["count"],
            item[0],
        ),
    )
    for code, entry in ordered:
        example = entry["problem"].replace("|", "\\|").replace("\n", " ")
        fix = entry["remediation"].replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| `{code}` | {entry['layer']} | {entry['severity']} | "
            f"{entry['count']} | {example} | {fix} |"
        )
    lines.extend(
        [
            "",
            "Errors are what the platform rejects. Warnings are pre-existing "
            "configuration debt, such as a `!BadRef` Quickbase wrote when the "
            "solution was exported; they do not block a deployment.",
        ]
    )
    return lines


def write_solution_summary(
    path: Path,
    label: str,
    qbl_version: str,
    parsed_data: Dict[str, Any],
    warnings: List[str],
    issues: List[Dict[str, Any]],
    has_table_schema: bool,
) -> None:
    counts = solution_counts(parsed_data)
    key_order = [
        "applications",
        "tables",
        "fields",
        "relationships",
        "roles",
        "permissions",
        "forms",
        "rules",
        "dashboards",
        "pages",
        "guides",
        "page_widgets",
        "reports",
        "charts",
        "report_groups",
        "pipelines",
        "pipeline_steps",
        "pipeline_table_matrix",
        "field_pipeline_matrix",
        "connected_tables",
        "connected_table_fields",
        "custom_emails",
        "custom_email_field_matrix",
        "custom_email_document_matrix",
        "document_templates",
        "parameter_definitions",
    ]
    unused_fields = sum(
        1
        for row in parsed_data.get("fields", [])
        if isinstance(row, dict) and str(row.get("Potentially Unused", "")).lower() == "yes"
    )
    duplicate_groups = len(
        {
            str(row.get("Duplicate Group"))
            for row in parsed_data.get("report_duplicates", [])
            if isinstance(row, dict) and row.get("Duplicate Group") not in (None, "")
        }
    )

    breakdown = issue_breakdown(issues)

    lines = [
        "# QBL Solution Overview",
        "",
        f"- Solution: `{label}`",
        f"- QBL version: `{qbl_version}`",
        f"- Parser warnings: {len(warnings)}",
        f"- Validation errors: {breakdown['errors']}",
        f"- Validation warnings: {breakdown['warnings']}",
        f"- Table schema supplied: {'Yes' if has_table_schema else 'No'}",
        "",
        "## Inventory",
        "",
        "| Collection | Rows |",
        "|---|---:|",
    ]
    for key in key_order:
        if key in counts:
            lines.append(f"| `{key}` | {counts[key]} |")
    for key in sorted(k for k in counts if k not in key_order and counts[k]):
        lines.append(f"| `{key}` | {counts[key]} |")

    relationship_rows = parsed_data.get("relationships") or []
    distinct = len(distinct_relationships(relationship_rows))
    if distinct != len(relationship_rows):
        lines.extend(
            [
                "",
                f"`relationships` has one row per side of each relationship: "
                f"{distinct} relationships in all.",
            ]
        )

    lines.extend(
        [
            "",
            "## Quality Signals",
            "",
            f"- Potentially unused fields: {unused_fields}",
            f"- Duplicate report groups: {duplicate_groups}",
            f"- Validation errors: {breakdown['errors']}",
            f"- Validation warnings: {breakdown['warnings']}",
        ]
    )
    lines.extend(render_validation_section(breakdown))
    if warnings:
        lines.extend(["", "## Parser Warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings[:100])
        if len(warnings) > 100:
            lines.append(f"- {len(warnings) - 100} more warnings are in `parsed-qbl.json`.")
    if not has_table_schema:
        lines.extend(
            [
                "",
                "## Enrichment Note",
                "",
                "Runtime table IDs and table metadata are blank because no table schema file was supplied.",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_summary(args: argparse.Namespace) -> Dict[str, Any]:
    qbl_file = validate_input(args.qbl_file, "QBL file")
    table_schema_file = validate_input(args.table_schema, "Table schema file")
    output_dir = prepare_output_dir(args.output_dir)

    qbl_data = load_qbl_file(qbl_file)
    qbl_version = detect_qbl_version(qbl_data)
    table_schema = load_optional_schema(table_schema_file)

    workflow_root = SCRIPT_DIR / "workflows" / "executive"
    sys.path.insert(0, str(workflow_root))
    from utils.executive_service import ExecutiveSummaryService  # type: ignore

    service = ExecutiveSummaryService(qbl_version)
    result = service.build_executive_summary(qbl_data, table_schema)
    parsed_data = plain(result.get("parsed_data", {}))
    issues = plain(result.get("issues", []))
    warnings = [str(item) for item in result.get("warnings", [])]

    label = args.label or qbl_file.stem
    workbook_path = output_dir / "solution-overview.xlsx"
    generate_solution_workbook(
        parsed_data,
        issues,
        workbook_path,
        label=label,
        qbl_version=qbl_version,
        warnings=warnings,
    )

    json_path = output_dir / "parsed-qbl.json"
    summary_path = output_dir / "solution-summary.md"
    digest_path = output_dir / "solution-digest.md"
    manifest_path = output_dir / "manifest.json"
    csv_files = write_collection_csvs(output_dir, parsed_data)

    write_json(
        json_path,
        {
            "source_file": qbl_file.name,
            "label": label,
            "qbl_version": qbl_version,
            "entity_counts": solution_counts(parsed_data),
            "warnings": warnings,
            "issues": issues,
            "parsed_data": parsed_data,
        },
    )
    write_solution_summary(
        summary_path,
        label,
        qbl_version,
        parsed_data,
        warnings,
        issues,
        bool(table_schema_file),
    )
    credential_findings = write_digest(
        digest_path,
        label=label,
        qbl_version=qbl_version,
        parsed_data=parsed_data,
        issues=issues,
        warnings=warnings,
        has_table_schema=bool(table_schema_file),
        inventory_path=json_path.name,
    )

    breakdown = issue_breakdown(issues)
    manifest = {
        "success": True,
        "workflow": "summary",
        "source_file": str(qbl_file),
        "qbl_version": qbl_version,
        "entity_counts": solution_counts(parsed_data),
        # `entity_counts.relationships` counts rows, and the export writes each
        # relationship on both of its tables. This is the number to report.
        "relationship_count": len(distinct_relationships(parsed_data.get("relationships") or [])),
        "warning_count": len(warnings),
        "validation_issue_count": len(issues),
        "validation_error_count": breakdown["errors"],
        "validation_warning_count": breakdown["warnings"],
        "validation_by_layer": breakdown["by_layer"],
        "possible_credential_count": len(credential_findings),
        "outputs": {
            "workbook": str(workbook_path),
            "json": str(json_path),
            "summary": str(summary_path),
            "digest": str(digest_path),
            "csv_files": csv_files,
        },
        "next_steps": {
            "read_first": str(digest_path),
            "list_collections": f"python3 {Path(__file__).name} collections \"{output_dir}\"",
            "example_query": (
                f"python3 {Path(__file__).name} query \"{output_dir}\" fields "
                '--where "Potentially Unused=Yes" --columns "Table Name,Field Label,Field Type"'
            ),
        },
    }
    bundle_path = output_dir / "qbl-solution-overview.zip"
    manifest["outputs"]["bundle"] = str(bundle_path)
    write_json(manifest_path, manifest)
    build_zip(output_dir, bundle_path.name)
    return manifest


def run_collections(args: argparse.Namespace) -> None:
    payload = load_inventory(args.inventory)
    print(describe_collections(payload, ENTITY_DESCRIPTIONS))


def run_query_command(args: argparse.Namespace) -> None:
    payload = load_inventory(args.inventory)
    columns = [c.strip() for c in args.columns.split(",") if c.strip()]
    result = run_query(
        payload,
        args.collection,
        filters=args.where,
        columns=columns or None,
        limit=None if args.limit is not None and args.limit < 0 else args.limit,
        distinct=args.distinct,
        count_only=args.count,
    )
    print(format_result(result, args.output_format))


def main() -> int:
    args = parse_args()
    try:
        if args.command == "collections":
            run_collections(args)
            return 0
        if args.command == "query":
            run_query_command(args)
            return 0
        manifest = run_summary(args)
        print(json.dumps(manifest, ensure_ascii=False, default=str))
        return 0
    except QueryError as exc:
        print(f"Query error: {exc}", file=sys.stderr)
        return 2
    except (FileNotFoundError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {"success": False, "error_type": type(exc).__name__, "message": str(exc)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(
            json.dumps(
                {"success": False, "error_type": type(exc).__name__, "message": str(exc)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
