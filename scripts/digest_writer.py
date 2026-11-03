"""Build the orientation document for a parsed QBL solution.

`parsed-qbl.json` grows with the solution and is too large to reason over
directly for anything but small applications. This module produces a digest of
what a reader needs to understand the solution.

Nothing here is sampled. A truncated list reads exactly like a complete one, and
Quickbase places no limit on how many tables, relationships, roles, or pipelines
a solution may contain, so any cap risks presenting a partial architecture as
though it were whole. Digest size therefore grows with the solution; that is the
intended trade. Use the `query` subcommand when a targeted answer is cheaper.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from secret_scanner import render_section, scan_parsed_data

# Structural inventories are listed in full. Quickbase does not limit how many
# tables, relationships, roles, or pipelines a solution may have, so truncating
# these would present an incomplete architecture as though it were complete --
# and a reader cannot tell the difference. Accuracy wins over context here.
NO_CAP = None

CAP_TABLES_PER_APP = NO_CAP
CAP_RELATIONSHIPS = NO_CAP
CAP_PIPELINES = NO_CAP
CAP_PIPELINE_REFS = NO_CAP
CAP_ENDPOINTS = NO_CAP
CAP_ROLES = NO_CAP
CAP_GENERIC = NO_CAP

CAP_UNUSED_FIELDS = NO_CAP


def _plural(count: int, noun: str) -> str:
    """Render a count with a naively pluralized noun."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _rows(data: Dict[str, Any], name: str) -> List[Dict[str, Any]]:
    value = data.get(name)
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _text(row: Dict[str, Any], *keys: str, default: str = "") -> str:
    """Return the first non-blank value among `keys`."""
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text != "N/A":
            return text
    return default


def _is_yes(row: Dict[str, Any], key: str) -> bool:
    return str(row.get(key, "")).strip().casefold() in ("yes", "true")


def _capped(
    lines: List[str],
    items: Sequence[str],
    cap: Optional[int],
    more_hint: str,
    indent: str = "- ",
) -> None:
    """Append every item, or the first `cap` of them when a cap is set.

    Every constant above is `NO_CAP` by default. When a cap is set, the list
    states how many rows it withheld and the query that returns them; a reader
    cannot otherwise distinguish a truncated list from a complete one.
    """
    if cap is None:
        lines.extend(f"{indent}{item}" for item in items)
        return

    lines.extend(f"{indent}{item}" for item in items[:cap])
    remaining = len(items) - cap
    if remaining > 0:
        lines.append(f"{indent}...and {remaining} more -- {more_hint}")


def _counts(data: Dict[str, Any]) -> Dict[str, int]:
    return {name: len(_rows(data, name)) for name in data if isinstance(data.get(name), list)}


def _architecture(lines: List[str], data: Dict[str, Any]) -> None:
    tables = _rows(data, "tables")
    fields = _rows(data, "fields")
    settings = _rows(data, "application_settings")
    roles = _rows(data, "roles")

    fields_by_table: Dict[str, int] = Counter()
    for row in fields:
        fields_by_table[_text(row, "Table Logical ID")] += 1

    tables_by_app: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in tables:
        tables_by_app[_text(row, "App Logical ID", default="(unassigned)")].append(row)

    app_names = {
        _text(row, "App Logical ID"): _text(row, "App Name")
        for row in settings
    }

    lines.extend(["## Architecture", ""])
    if not tables_by_app:
        lines.extend(["No tables were found in this export.", ""])
        return

    for app_key in sorted(tables_by_app):
        app_tables = tables_by_app[app_key]
        label = app_names.get(app_key, "")
        heading = f"### {label} (`{app_key}`)" if label else f"### `{app_key}`"
        lines.extend([heading, "", f"{_plural(len(app_tables), 'table')}:", ""])

        entries = []
        for row in sorted(app_tables, key=lambda r: _text(r, "Table Name")):
            logical = _text(row, "Table Logical ID")
            name = _text(row, "Table Name", default=logical)
            table_id = _text(row, "Table ID")
            parts = [f"**{name}** (`{logical}`"]
            if table_id:
                parts.append(f", id `{table_id}`")
            parts.append(f") -- {_plural(fields_by_table.get(logical, 0), 'field')}")
            if _is_yes(row, "Custom Data Rule Enabled?"):
                parts.append(", custom data rule enabled")
            entries.append("".join(parts))
        _capped(
            lines,
            entries,
            CAP_TABLES_PER_APP,
            f"query the `tables` collection filtered on `App Logical ID={app_key}`",
        )
        lines.append("")

    relationships = _rows(data, "relationships")
    if relationships:
        lines.extend([f"### Relationships ({len(relationships)})", ""])
        entries = []
        for row in relationships:
            parent = _text(row, "Parent Table Name", "Parent Table Logical ID", default="?")
            child = _text(row, "Child Table Name", "Child Table Logical ID", default="?")
            logical = _text(row, "Relationship Logical ID")
            ref_count = _text(row, "Total Reference Fields", default="0")
            cross = " [cross-app]" if _is_yes(row, "Cross App") else ""
            detail = f"`{logical}`" if logical else ""
            if ref_count and ref_count != "0":
                detail += (", " if detail else "") + _plural(int(ref_count), "referencing field")
            entries.append(f"{parent} -> {child}" + (f" ({detail})" if detail else "") + cross)
        _capped(lines, entries, CAP_RELATIONSHIPS, "query the `relationships` collection")
        lines.append("")

    if roles:
        lines.extend([f"### Roles ({len(roles)})", ""])
        entries = []
        for row in roles:
            name = _text(row, "Role Name", "Role Logical ID", default="?")
            flags = [
                label
                for key, label in (
                    ("Edit App", "edit app"),
                    ("Manage Users", "manage users"),
                    ("Disable Access", "access disabled"),
                    ("Default Role", "default"),
                )
                if _is_yes(row, key)
            ]
            entries.append(f"{name}" + (f" ({', '.join(flags)})" if flags else ""))
        _capped(lines, entries, CAP_ROLES, "query the `roles` collection")
        lines.append("")


def _integration_surface(lines: List[str], data: Dict[str, Any]) -> None:
    pipelines = _rows(data, "pipelines")
    steps = _rows(data, "pipeline_steps")
    pipeline_tables = _rows(data, "pipeline_table_matrix")
    pipeline_fields = _rows(data, "field_pipeline_matrix")
    connected = _rows(data, "connected_tables")
    external = _rows(data, "external_resources")

    lines.extend(["## Integration surface", ""])

    steps_by_pipeline: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in steps:
        steps_by_pipeline[_text(row, "Pipeline Logical ID")].append(row)

    tables_by_pipeline: Dict[str, set] = defaultdict(set)
    for row in pipeline_tables:
        name = _text(row, "Table Name", "Table Logical ID")
        if name:
            tables_by_pipeline[_text(row, "Pipeline Logical ID")].add(name)

    fields_by_pipeline: Dict[str, set] = defaultdict(set)
    for row in pipeline_fields:
        name = _text(row, "Field Label", "Field Logical ID")
        if name:
            fields_by_pipeline[_text(row, "Pipeline Logical ID")].add(name)

    if pipelines:
        lines.extend([f"### Pipelines ({len(pipelines)})", ""])
        blocks: List[str] = []
        for row in sorted(pipelines, key=lambda r: _text(r, "Pipeline Name")):
            key = _text(row, "Pipeline Logical ID")
            name = _text(row, "Pipeline Name", default=key)
            own_steps = steps_by_pipeline.get(key, [])
            subtypes = [s for s in (_text(s, "Step SubType") for s in own_steps) if s]

            entry = [f"**{name}** (`{key}`) -- {_text(row, 'Total Steps', default=str(len(own_steps)))} steps"]
            owner = _text(row, "Owner")
            if owner:
                entry.append(f"owner: {owner}")
            if subtypes:
                counted = Counter(subtypes)
                entry.append("actions: " + ", ".join(f"{k} x{v}" if v > 1 else k for k, v in counted.most_common()))
            touched_tables = sorted(tables_by_pipeline.get(key, ()))
            if touched_tables:
                entry.append(f"tables: {', '.join(touched_tables)}")
            touched_fields = sorted(fields_by_pipeline.get(key, ()))
            if touched_fields:
                entry.append(f"fields: {', '.join(touched_fields)}")
            blocks.append("; ".join(entry))
        _capped(lines, blocks, CAP_PIPELINES, "query the `pipelines` collection")
        lines.append("")

    endpoints = []
    for row in steps:
        url = _text(row, "HTTP URL")
        if url:
            method = _text(row, "HTTP Method", default="?")
            pipeline = _text(row, "Pipeline Name", "Pipeline Logical ID")
            endpoints.append(f"{method} {url}  (`{pipeline}` step {_text(row, 'Step ID')})")
    if endpoints:
        lines.extend([f"### Outbound HTTP calls ({len(endpoints)})", ""])
        _capped(
            lines,
            endpoints,
            CAP_ENDPOINTS,
            "query `pipeline_steps` filtered on `HTTP URL!=`",
        )
        lines.append("")

    channels = Counter(
        _text(row, "Channel Resource") for row in steps if _text(row, "Channel Resource")
    )
    if channels:
        lines.extend(["### Channels in use", ""])
        lines.extend(f"- {name}: {_plural(count, 'step')}" for name, count in channels.most_common())
        lines.append("")

    if connected:
        lines.extend([f"### Connected tables ({len(connected)})", ""])
        entries = [
            _text(row, "Connected Table Name", "Table Name", "Connected Table Logical ID", default="?")
            for row in connected
        ]
        _capped(lines, entries, CAP_GENERIC, "query the `connected_tables` collection")
        lines.append("")

    if external:
        lines.extend([f"### External resources ({len(external)})", ""])
        entries = [_text(row, "Name", "Resource Name", default="?") for row in external]
        _capped(lines, entries, CAP_GENERIC, "query the `external_resources` collection")
        lines.append("")

    if not any((pipelines, endpoints, connected, external)):
        lines.extend(["No pipelines, outbound calls, connected tables, or external resources were found.", ""])


def _logic_and_automation(lines: List[str], data: Dict[str, Any]) -> None:
    fields = _rows(data, "fields")
    counts = _counts(data)

    formula_fields = [r for r in fields if _text(r, "Formula")]
    formula_queries = [r for r in fields if _is_yes(r, "Is Formula Query")]
    lookups = [r for r in fields if _text(r, "Lookup Target Field")]
    summaries = [r for r in fields if _text(r, "Summary Target Field")]
    cached = [r for r in fields if str(r.get("Field Caching Enabled", "")).strip().casefold() == "yes"]

    lines.extend(
        [
            "## Logic and automation",
            "",
            f"- Formula fields: {len(formula_fields)}",
            f"- Formula-query fields: {len(formula_queries)}",
            f"- Lookup fields: {len(lookups)}",
            f"- Summary fields: {len(summaries)}",
            f"- Fields with caching enabled: {len(cached)}",
            f"- Form rules: {counts.get('rules', 0)}",
            f"- Custom emails: {counts.get('custom_emails', 0)}",
            f"- Document templates: {counts.get('document_templates', 0)}",
            f"- Code pages: {counts.get('pages', 0)}",
            f"- Home page widgets: {counts.get('page_widgets', 0)}",
            f"- App guides: {counts.get('guides', 0)}",
            "",
            "Read a specific formula with: `query fields --where \"Field Logical ID=<id>\" --columns \"Field Label,Formula\"`",
            "",
        ]
    )


def _cross_reference_sources(data: Dict[str, Any]) -> Dict[str, set]:
    """Map each cross-reference collection to the field logical IDs it mentions.

    The parser's own usage flags cover reports, forms, rules, formulas,
    relationships, dashboards, charts, field properties, and permissions, and its
    cross-reference pass extends them to pipelines, custom emails, and
    connected tables. Scanning every collection that carries a field logical ID
    is the generic backstop over all of that: it needs no per-collection mapping,
    so a collection a later QBL version adds is covered the day it appears.
    """
    sources: Dict[str, set] = {}
    for name, rows in data.items():
        if name == "fields" or not isinstance(rows, list):
            continue
        referenced = {
            _text(row, "Field Logical ID")
            for row in rows
            if isinstance(row, dict) and _text(row, "Field Logical ID")
        }
        if referenced:
            sources[name] = referenced
    return sources


def _severity_count(issues: Sequence[Dict[str, Any]], severity: str) -> int:
    """How many findings carry this severity, defaulting a blank one to error."""
    return sum(
        1
        for issue in issues
        if str(issue.get("Severity", "error") or "error").lower() == severity
    )


def _validation_findings(lines: List[str], issues: Sequence[Dict[str, Any]]) -> None:
    """List the distinct validation findings, each with its fix.

    Grouped by code rather than by node type. A large export is usually a dozen
    distinct problems repeated across hundreds of nodes, and the fix is per
    code - so a list of node types tells a reader how widespread the damage is
    but never what to do about it. Errors are what the platform rejects;
    warnings are pre-existing debt, most often a `!BadRef` Quickbase itself
    wrote when the solution was exported, and they deploy fine.
    """
    if not issues:
        return

    grouped: Dict[str, Dict[str, Any]] = {}
    for issue in issues:
        code = str(issue.get("Code", "") or "")
        entry = grouped.setdefault(
            code,
            {
                "count": 0,
                "layer": str(issue.get("Layer", "") or "Other"),
                "severity": str(issue.get("Severity", "error") or "error").lower(),
                "problem": str(issue.get("Problem", "")),
                "remediation": str(issue.get("Remediation", "")),
                "paths": [],
            },
        )
        entry["count"] += 1
        # Distinct paths only. Several findings under one code often share a
        # path - three missing built-in fields all sit on the same `Fields`
        # container - and repeating it says nothing about where else to look.
        path = str(issue.get("Path", "") or "")
        if path and len(entry["paths"]) < 3 and path not in entry["paths"]:
            entry["paths"].append(path)

    ordered = sorted(
        grouped.items(),
        key=lambda item: (
            0 if item[1]["severity"] == "error" else 1,
            -item[1]["count"],
            item[0],
        ),
    )

    lines.append("### Validation findings")
    lines.append("")
    for code, entry in ordered[:CAP_GENERIC] if CAP_GENERIC else ordered:
        lines.append(
            f"- `{code}` ({entry['layer']}, {entry['severity']}) "
            f"x{entry['count']} -- {entry['problem']}"
        )
        if entry["remediation"]:
            lines.append(f"  - Fix: {entry['remediation']}")
        for path in entry["paths"]:
            lines.append(f"  - at `{path}`")
    lines.append("")


def _quality_signals(lines: List[str], data: Dict[str, Any], issues: Sequence[Dict[str, Any]]) -> None:
    fields = _rows(data, "fields")
    flagged = [r for r in fields if _is_yes(r, "Potentially Unused")]
    duplicates = _rows(data, "report_duplicates")

    # Split the flagged fields by whether any cross-reference collection still
    # mentions them. Recommending deletion of the second group would break a
    # live reference.
    sources = _cross_reference_sources(data)
    referenced_elsewhere: Dict[str, List[str]] = {}
    for row in flagged:
        logical = _text(row, "Field Logical ID")
        hits = sorted(name for name, ids in sources.items() if logical in ids)
        if hits:
            referenced_elsewhere[logical] = hits
    unreferenced = [
        r for r in flagged if _text(r, "Field Logical ID") not in referenced_elsewhere
    ]

    lines.extend(
        [
            "## Quality signals",
            "",
            f"- Fields flagged `Potentially Unused`: {len(flagged)} of {len(fields)}",
            f"  - with no reference in any collection: {len(unreferenced)}",
            f"  - still referenced elsewhere (flag is a false positive): {len(referenced_elsewhere)}",
            f"- Duplicate report groups: "
            f"{len({_text(r, 'Duplicate Group') for r in duplicates if _text(r, 'Duplicate Group')})}",
            f"- Validation errors: {_severity_count(issues, 'error')}",
            f"- Validation warnings: {_severity_count(issues, 'warning')}",
            "",
        ]
    )

    _validation_findings(lines, issues)

    if referenced_elsewhere:
        lines.extend(
            [
                "### Flagged unused but still referenced -- do not recommend deleting these",
                "",
                "The usage flags cover the surfaces the parser maps to a named usage",
                "category. This scan is broader: it reads every collection carrying a",
                "field logical ID, including ones a later QBL version adds. These fields",
                "are flagged unused yet appear in a cross-reference collection:",
                "",
            ]
        )
        label_by_logical = {
            _text(r, "Field Logical ID"): (
                f"{_text(r, 'Table Name', 'Table Logical ID')} / "
                f"{_text(r, 'Field Label', 'Field Logical ID')}"
            )
            for r in flagged
        }
        entries = [
            f"{label_by_logical.get(logical, logical)} (`{logical}`) -- referenced in {', '.join(hits)}"
            for logical, hits in sorted(referenced_elsewhere.items())
        ]
        _capped(lines, entries, CAP_UNUSED_FIELDS, "cross-check the matrix collections per field")
        lines.append("")

    if unreferenced:
        lines.extend(
            [
                "### No reference found in any collection",
                "",
                "Review candidates only. A code page, URL formula, or external integration",
                "can reference a field in ways a QBL export does not record.",
                "",
            ]
        )
        entries = [
            f"{_text(r, 'Table Name', 'Table Logical ID')} / "
            f"{_text(r, 'Field Label', 'Field Logical ID')} ({_text(r, 'Field Type')})"
            for r in unreferenced
        ]
        _capped(
            lines,
            entries,
            CAP_UNUSED_FIELDS,
            'query `fields --where "Potentially Unused=Yes"`',
        )
        lines.append("")


def _inventory_table(lines: List[str], data: Dict[str, Any]) -> None:
    counts = {name: count for name, count in _counts(data).items() if count}
    lines.extend(["## Full inventory counts", "", "| Collection | Rows |", "|---|---:|"])
    for name in sorted(counts):
        lines.append(f"| `{name}` | {counts[name]} |")
    lines.append("")


def write_digest(
    path: Path,
    *,
    label: str,
    qbl_version: str,
    parsed_data: Dict[str, Any],
    issues: Sequence[Dict[str, Any]],
    warnings: Sequence[str],
    has_table_schema: bool,
    inventory_path: str,
) -> List[Dict[str, str]]:
    """Write the orientation digest and return any credential findings."""
    lines: List[str] = [
        f"# Solution Digest: {label}",
        "",
        f"- QBL version: `{qbl_version}`",
        f"- Table schema supplied: {'yes' if has_table_schema else 'no (runtime table IDs are blank)'}",
        f"- Parser warnings: {len(warnings)}",
        f"- Validation errors: {_severity_count(issues, 'error')}",
        f"- Validation warnings: {_severity_count(issues, 'warning')}",
        "",
        "Every list below is complete, not sampled. The full row-level inventory is",
        f"in `{inventory_path}` alongside this file; query it rather than reading it whole.",
        "",
    ]

    # Credential warnings lead, ahead of the architecture, because they are the
    # one section that is urgent rather than descriptive.
    credential_findings = scan_parsed_data(parsed_data)
    lines.extend(render_section(credential_findings))

    _architecture(lines, parsed_data)
    _integration_surface(lines, parsed_data)
    _logic_and_automation(lines, parsed_data)
    _quality_signals(lines, parsed_data, issues)
    _inventory_table(lines, parsed_data)

    path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    return credential_findings
