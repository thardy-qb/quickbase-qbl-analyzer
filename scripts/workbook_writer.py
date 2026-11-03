"""Create QBL analysis workbooks with the bundled XlsxWriter package."""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

import xlsxwriter

EXCEL_MAX_ROWS = 1_048_576
EXCEL_MAX_COLS = 16_384
INVALID_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")


def _display_name(value: str) -> str:
    return value.replace("_", " ").strip().title()


def _sheet_name(raw_name: str, used: set[str]) -> str:
    base = INVALID_SHEET_CHARS.sub(" ", raw_name).strip().strip("'") or "Sheet"
    base = re.sub(r"\s+", " ", base)[:31]
    candidate = base
    counter = 2
    while candidate.casefold() in used:
        suffix = f" {counter}"
        candidate = f"{base[:31-len(suffix)]}{suffix}"
        counter += 1
    used.add(candidate.casefold())
    return candidate


def _cell_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
    return str(value)


def _flatten_mapping(row: Mapping[str, Any]) -> OrderedDict[str, Any]:
    flattened: OrderedDict[str, Any] = OrderedDict()
    for key, value in row.items():
        flattened[str(key)] = _cell_value(value)
    return flattened


def _coerce_rows(rows: Any) -> List[OrderedDict[str, Any]]:
    if rows is None:
        return []
    if isinstance(rows, Mapping):
        rows = [rows]
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        rows = [{"Value": rows}]

    output: List[OrderedDict[str, Any]] = []
    for item in rows:
        if isinstance(item, Mapping):
            output.append(_flatten_mapping(item))
        else:
            output.append(OrderedDict([("Value", _cell_value(item))]))
    return output


def _headers(rows: Iterable[Mapping[str, Any]]) -> List[str]:
    ordered: OrderedDict[str, None] = OrderedDict()
    for row in rows:
        for key in row.keys():
            ordered.setdefault(str(key), None)
    return list(ordered.keys())[:EXCEL_MAX_COLS]


def _formats(workbook: xlsxwriter.Workbook) -> Dict[str, Any]:
    return {
        "title": workbook.add_format(
            {"bold": True, "font_size": 18, "font_color": "#FFFFFF", "bg_color": "#17365D", "align": "left", "valign": "vcenter"}
        ),
        "subtitle": workbook.add_format(
            {"italic": True, "font_color": "#44546A", "text_wrap": True, "valign": "top"}
        ),
        "section": workbook.add_format(
            {"bold": True, "font_size": 12, "font_color": "#FFFFFF", "bg_color": "#4472C4", "align": "left"}
        ),
        "header": workbook.add_format(
            {"bold": True, "font_color": "#FFFFFF", "bg_color": "#5B9BD5", "border": 1, "text_wrap": True, "valign": "top"}
        ),
        "cell": workbook.add_format({"border": 1, "valign": "top"}),
        "wrap": workbook.add_format({"border": 1, "valign": "top", "text_wrap": True}),
        "integer": workbook.add_format({"border": 1, "valign": "top", "num_format": "0"}),
        "warning": workbook.add_format({"border": 1, "valign": "top", "bg_color": "#FFF2CC", "text_wrap": True}),
        "link": workbook.add_format({"font_color": "#0563C1", "underline": True, "border": 1, "valign": "top"}),
    }


def _write_value(worksheet: Any, row: int, col: int, value: Any, formats: Dict[str, Any]) -> None:
    if isinstance(value, bool):
        worksheet.write_boolean(row, col, value, formats["cell"])
        return
    if isinstance(value, int) and not isinstance(value, bool):
        worksheet.write_number(row, col, value, formats["integer"])
        return
    if isinstance(value, float):
        worksheet.write_number(row, col, value, formats["cell"])
        return

    text = "" if value is None else str(value)
    worksheet.write_string(row, col, text, formats["wrap"])


def _write_table_sheet(
    workbook: xlsxwriter.Workbook,
    used_names: set[str],
    name: str,
    rows: Any,
    formats: Dict[str, Any],
) -> int:
    normalized_rows = _coerce_rows(rows)
    worksheet = workbook.add_worksheet(_sheet_name(name, used_names))
    worksheet.hide_gridlines(2)

    if not normalized_rows:
        worksheet.write(0, 0, "No records", formats["section"])
        worksheet.set_column(0, 0, 30)
        return 0

    normalized_rows = normalized_rows[: EXCEL_MAX_ROWS - 1]
    headers = _headers(normalized_rows)
    for col, header in enumerate(headers):
        worksheet.write(0, col, header, formats["header"])

    widths = [max(10, min(60, len(header) + 2)) for header in headers]
    for row_index, row in enumerate(normalized_rows, start=1):
        for col, header in enumerate(headers):
            value = row.get(header, "")
            _write_value(worksheet, row_index, col, value, formats)
            widths[col] = min(60, max(widths[col], min(60, len(str(value)) + 2)))

    worksheet.freeze_panes(1, 0)
    worksheet.autofilter(0, 0, len(normalized_rows), max(0, len(headers) - 1))
    for col, width in enumerate(widths):
        worksheet.set_column(col, col, width)
    worksheet.set_row(0, 30)
    return len(normalized_rows)


def generate_solution_workbook(
    parsed_data: Mapping[str, Any],
    issues: Sequence[Mapping[str, Any]],
    output_path: Path | str,
    *,
    label: str,
    qbl_version: str,
    warnings: Sequence[str] = (),
) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(
        str(output),
        {"strings_to_formulas": False, "strings_to_urls": False, "use_zip64": True},
    )
    formats = _formats(workbook)
    used_names: set[str] = set()

    overview = workbook.add_worksheet(_sheet_name("Overview", used_names))
    overview.hide_gridlines(2)
    overview.set_column(0, 0, 30)
    overview.set_column(1, 1, 18)
    overview.set_column(2, 2, 75)
    overview.merge_range(0, 0, 0, 2, "QBL Solution Overview", formats["title"])
    overview.set_row(0, 28)
    overview.write(2, 0, "Solution", formats["header"])
    overview.write(2, 1, label, formats["wrap"])
    overview.write(3, 0, "QBL Version", formats["header"])
    overview.write(3, 1, qbl_version, formats["wrap"])
    overview.write(5, 0, "Collection", formats["header"])
    overview.write(5, 1, "Records", formats["header"])
    overview.write(5, 2, "Status", formats["header"])

    summary_row = 6
    collections: List[tuple[str, Any]] = []
    for key, value in parsed_data.items():
        count = len(value) if isinstance(value, list) else (1 if value else 0)
        overview.write(summary_row, 0, _display_name(str(key)), formats["cell"])
        overview.write_number(summary_row, 1, count, formats["integer"])
        overview.write(summary_row, 2, "Included" if count else "Empty", formats["cell"])
        if count:
            collections.append((str(key), value))
        summary_row += 1

    # Errors and warnings are counted apart. The parser runs five validation
    # layers, and a `!BadRef` Quickbase itself left in the export is a
    # warning that will not block a deployment - rolled into one total, it
    # reads as a defect the reader has to go and fix.
    error_count = sum(
        1
        for issue in issues
        if str(issue.get("Severity", "error") or "error").lower() == "error"
    )
    warning_count = len(issues) - error_count

    overview.write(summary_row, 0, "Validation Errors", formats["cell"])
    overview.write_number(summary_row, 1, error_count, formats["integer"])
    overview.write(
        summary_row,
        2,
        "Attention" if error_count else "Clean",
        formats["warning"] if error_count else formats["cell"],
    )
    summary_row += 1

    overview.write(summary_row, 0, "Validation Warnings", formats["cell"])
    overview.write_number(summary_row, 1, warning_count, formats["integer"])
    overview.write(summary_row, 2, "Review" if warning_count else "Clean", formats["cell"])
    summary_row += 2

    if warnings:
        overview.write(summary_row, 0, "Warnings", formats["section"])
        summary_row += 1
        for warning in warnings[:100]:
            overview.merge_range(summary_row, 0, summary_row, 2, str(warning), formats["warning"])
            summary_row += 1

    overview.freeze_panes(6, 0)
    overview.autofilter(5, 0, max(5, 5 + len(parsed_data)), 2)

    for key, value in collections:
        _write_table_sheet(workbook, used_names, _display_name(key), value, formats)
    if issues:
        _write_table_sheet(workbook, used_names, "Validation Issues", issues, formats)

    workbook.close()


