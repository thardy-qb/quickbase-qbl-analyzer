"""Index the table, field and role identifiers in a QBL export.

Each field node declares its `Id`, each role node declares its `Id` and name,
and each table declares an `AliasHint`. This module collects them from the
parsed document, per application.

`build_parser_index` returns them in the form `parse_qbl_data` takes.
"""

from __future__ import annotations

from typing import Any, Dict


def _mapping(value: Any, key: str) -> Dict[str, Any]:
    """The mapping at `key`, or an empty one for any other shape."""
    if not isinstance(value, dict):
        return {}
    nested = value.get(key)
    return nested if isinstance(nested, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def build_index(qbl_data: Any) -> Dict[str, Dict[str, Any]]:
    """Collect the field, role and table-alias identifiers declared in an export.

    Returns::

        {app logical id: {
            "tables": {table logical id: {"alias": str, "fields": {...}}},
            "roles": {role logical id: {"id": str, "name": str}},
        }}

    `alias` is the table's `AliasHint`, which is the join key to an optional
    Quickbase table schema payload carrying runtime table IDs and names. Field
    and role entries carry the `Id` the export declares for them.
    """
    index: Dict[str, Dict[str, Any]] = {}

    for app_key, app_value in _mapping(qbl_data, "Resources").items():
        if not isinstance(app_value, dict) or not str(app_key).startswith("$App_"):
            continue

        tables: Dict[str, Any] = {}
        for table_key, table_value in _mapping(app_value, "Tables").items():
            if not isinstance(table_value, dict):
                continue

            fields: Dict[str, Dict[str, str]] = {}
            for field_key, field_value in _mapping(table_value, "Fields").items():
                if not isinstance(field_value, dict):
                    continue
                fields[field_key] = {
                    "id": _text(field_value.get("Id")),
                    "label": _text(_mapping(field_value, "Properties").get("Label")),
                }

            tables[table_key] = {
                "alias": _text(_mapping(table_value, "Properties").get("AliasHint")),
                "fields": fields,
            }

        roles: Dict[str, Dict[str, str]] = {}
        for role_key, role_value in _mapping(app_value, "Roles").items():
            if not isinstance(role_value, dict):
                continue
            roles[role_key] = {
                "id": _text(role_value.get("Id")),
                "name": _text(_mapping(role_value, "Properties").get("Name")),
            }

        index[app_key] = {"tables": tables, "roles": roles}

    return index


def as_parser_index(index: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Arrange the index in the form `parse_qbl_data` takes."""
    adapted: Dict[str, Dict[str, Any]] = {}
    for app_key, app_value in (index or {}).items():
        tables = {
            table_key: {
                "id": table_value.get("alias", ""),
                "elements": table_value.get("fields", {}),
            }
            for table_key, table_value in _mapping(app_value, "tables").items()
        }
        adapted[app_key] = {"tables": tables, "roles": _mapping(app_value, "roles")}
    return adapted


def build_parser_index(qbl_data: Any) -> Dict[str, Dict[str, Any]]:
    """The identifiers in `qbl_data`, in the shape `parse_qbl_data` reads."""
    return as_parser_index(build_index(qbl_data))
