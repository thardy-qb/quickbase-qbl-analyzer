import json
from collections import defaultdict
from typing import Dict, Any, List

from qblparser import VALIDATE_ALL, parse_qbl_data, remediation_for
from utils.helpers import SafeExtractor
from qbl_index import build_parser_index


# Which validation layer produced a finding, read off its code prefix. The
# layers answer different questions, and a reader triaging 200 findings needs
# to know whether they are looking at a malformed node, a reference that does
# not resolve, or a formula naming a field that does not exist.
ISSUE_LAYERS = {
    "SCH": "Schema",
    "REF": "Reference",
    "VAL": "Value",
    "STR": "Structure",
    "FML": "Formula",
}


FORM_QBL_PROPERTY_COLUMNS = {
    "WaitForEmbeddedReports": "Wait For Embedded Reports",
    "NewFieldAction": "New Field Action",
}


class ExecutiveSummaryService:
    """
    Handles parser invocation, validation, and summary enrichment.

    The QBL parser does the structural parsing. This service adds the
    summary datasets and columns that sit outside the parsed collections.
    """

    def __init__(self, qbl_version):
        self.qbl_version = qbl_version

    def build_executive_summary(self, qbl_data, table_schema=None):
        """Produce the executive summary bundle."""
        parse_result = parse_qbl_data(
            qbl_data,
            qbl_version=self.qbl_version,
            table_schema=table_schema,
            # The export declares its own field and role IDs and its table
            # aliases; `scripts/qbl_index.py` reads them out of the file.
            identifier_index=build_parser_index(qbl_data),
            capture_warnings=True,
            # Run all five validation layers. Each catches failures the others
            # pass: a `!Ref` that resolves to nothing, a `!BadRef` Quickbase
            # itself left behind, a formula naming a field that does
            # not exist, an app with no home page.
            validate=VALIDATE_ALL,
        )
        parsed_data = parse_result.parsed_data
        self._apply_form_qbl_properties(parsed_data, qbl_data)
        self._apply_relationship_table_ids(parsed_data)

        issues = self._annotate_issues(parse_result.issues or [])
        parser_warnings = [
            {"Warning": warning}
            for warning in (parse_result.warnings or [])
            if str(warning).strip()
        ]
        if parser_warnings:
            parsed_data["parser_warnings"] = parser_warnings

        additional_datasets = self._extract_additional_metadata(qbl_data)
        for key, value in additional_datasets.items():
            if value:
                parsed_data[key] = value

        duplicate_reports = self._find_duplicate_reports(parsed_data)
        if duplicate_reports:
            parsed_data["report_duplicates"] = duplicate_reports

        return {
            "qbl_data": qbl_data,
            "parsed_data": parsed_data,
            "issues": issues,
            "warnings": list(parse_result.warnings or []),
            "table_schema": table_schema,
        }

    def _annotate_issues(self, issues) -> List[Dict[str, Any]]:
        """Add the layer and the fix to each validation finding.

        A finding states a defect; it does not say what to do about it, and for
        several of these codes the obvious response is the wrong one. Quickbase
        skips an unrecognised type with a warning rather than rejecting the
        document, so the object is simply missing - and "unknown resource type"
        invites filling in more properties when the only fix is correcting the
        name. The parser records the procedure per
        code; this carries it onto the row so a reader never has to look it up.
        """
        annotated = []
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            row = dict(issue)
            code = self._text_or_blank(row.get("Code", ""))
            row["Code"] = code
            row["Layer"] = ISSUE_LAYERS.get(code[:3], "Other")
            # `Severity` is present on every layer's output, but default it
            # rather than trust that: a blank severity would sort a real error
            # in with pre-existing debt.
            row["Severity"] = self._text_or_blank(row.get("Severity", "")) or "error"
            row["Remediation"] = remediation_for(code)
            annotated.append(row)

        severity_rank = {"error": 0, "warning": 1}
        annotated.sort(
            key=lambda row: (
                severity_rank.get(row["Severity"], 2),
                row["Code"],
                self._text_or_blank(row.get("Path", "")),
            )
        )
        return annotated

    def _apply_relationship_table_ids(self, parsed_data: Dict[str, Any]) -> None:
        """Add parent and child DBIDs to parser-emitted relationship rows.

        Table DBIDs are already resolved in the Tables dataset by matching the
        QBL alias to the table-schema payload.  Relationships retain logical
        IDs, so this enrichment joins them back to that resolved inventory.  App scope is required because a logical
        table ID may appear in more than one application.
        """
        relationship_rows = parsed_data.get("relationships")
        table_rows = parsed_data.get("tables")
        if not isinstance(relationship_rows, list) or not isinstance(table_rows, list):
            return

        table_id_by_app_logical = {}
        logical_id_candidates = defaultdict(list)
        for table_row in table_rows:
            if not isinstance(table_row, dict):
                continue
            app_logical_id = self._text_or_blank(table_row.get("App Logical ID", ""))
            table_logical_id = self._text_or_blank(table_row.get("Table Logical ID", ""))
            table_id = self._text_or_blank(table_row.get("Table ID", ""))
            if not table_logical_id or not table_id:
                continue
            if app_logical_id:
                table_id_by_app_logical[(app_logical_id, table_logical_id)] = table_id
            logical_id_candidates[table_logical_id].append(table_id)

        unique_table_id_by_logical = {
            table_logical_id: table_ids[0]
            for table_logical_id, table_ids in logical_id_candidates.items()
            if len(set(table_ids)) == 1
        }

        for relationship_row in relationship_rows:
            if not isinstance(relationship_row, dict):
                continue
            relationship_app_logical_id = self._text_or_blank(
                relationship_row.get("App Logical ID", "")
            )
            for role in ("Parent", "Child"):
                app_logical_id = self._text_or_blank(
                    relationship_row.get(f"{role} App Logical ID", "")
                ) or relationship_app_logical_id
                table_logical_id = self._text_or_blank(
                    relationship_row.get(f"{role} Table Logical ID", "")
                )
                table_id = table_id_by_app_logical.get(
                    (app_logical_id, table_logical_id), ""
                ) or unique_table_id_by_logical.get(table_logical_id, "")
                relationship_row[f"{role} Table ID"] = table_id

    def _apply_form_qbl_properties(self, parsed_data: Dict[str, Any], qbl_data: Dict[str, Any]) -> None:
        """Attach form properties that sit outside the parsed form collection."""
        forms = parsed_data.get("forms")
        if not isinstance(forms, list) or not forms:
            return

        properties_by_form = self._collect_form_qbl_properties(qbl_data)
        # Prefer app/table/form scoped matches. The fallback handles parser rows
        # that only carry the form logical ID, but only when that ID is unique.
        fallback_by_form = {}
        duplicate_form_keys = set()
        for (_, _, form_key), values in properties_by_form.items():
            if not form_key:
                continue
            if form_key in fallback_by_form:
                duplicate_form_keys.add(form_key)
            else:
                fallback_by_form[form_key] = values
        for form_key in duplicate_form_keys:
            fallback_by_form.pop(form_key, None)

        for form_row in forms:
            if not isinstance(form_row, dict):
                continue

            form_key = (
                form_row.get("App Logical ID", ""),
                form_row.get("Table Logical ID", ""),
                form_row.get("Form Logical ID", ""),
            )
            property_values = properties_by_form.get(form_key) or fallback_by_form.get(form_key[2], {})

            for column_name in FORM_QBL_PROPERTY_COLUMNS.values():
                form_row[column_name] = property_values.get(column_name, "")

    def _collect_form_qbl_properties(self, qbl_data: Dict[str, Any]) -> Dict[tuple, Dict[str, Any]]:
        form_properties = {}
        resources = qbl_data.get("Resources", {}) if isinstance(qbl_data, dict) else {}

        for app_key, app_value in resources.items():
            if not isinstance(app_value, dict) or not app_key.startswith("$App_"):
                continue

            tables = app_value.get("Tables", {})
            if not isinstance(tables, dict):
                continue

            for table_key, table_value in tables.items():
                if not isinstance(table_value, dict):
                    continue

                forms_node = SafeExtractor.get_dict(table_value, "Forms")
                forms = SafeExtractor.get_dict(forms_node, "Resources")
                if not forms:
                    forms = {
                        key: value
                        for key, value in forms_node.items()
                        if isinstance(key, str) and key.startswith(("$Form_", "$FormV2_"))
                    }

                for form_key, form_value in forms.items():
                    if not isinstance(form_value, dict):
                        continue

                    props = SafeExtractor.get_dict(form_value, "Properties")
                    form_properties[(app_key, table_key, form_key)] = {
                        column_name: self._stringify_ref_value(props.get(property_name, ""))
                        for property_name, column_name in FORM_QBL_PROPERTY_COLUMNS.items()
                    }

        return form_properties

    def _extract_additional_metadata(self, qbl_data: Dict[str, Any]) -> Dict[str, Any]:
        """Collect supplemental datasets outside the parsed collections."""
        additional = {
            "parameter_definitions": self._parse_parameter_definitions(qbl_data),
            "application_settings": self._parse_application_settings(qbl_data),
            "application_variables": self._parse_application_variables(qbl_data),
            "external_resources": [],
            "external_resource_recordsets": [],
            "external_resource_columns": [],
        }

        resources, recordsets, columns = self._parse_external_resources(qbl_data)
        additional["external_resources"] = resources
        additional["external_resource_recordsets"] = recordsets
        additional["external_resource_columns"] = columns

        return additional

    def _parse_parameter_definitions(self, qbl_data: Dict[str, Any]) -> list:
        params = []
        param_defs = qbl_data.get("ParameterDefinitions", {})
        for param_key, param_value in param_defs.items():
            if not isinstance(param_value, dict):
                continue
            params.append({
                "Parameter Logical ID": param_key,
                "Type": param_value.get("Type", ""),
                "Description": param_value.get("Description", ""),
                "Value": self._stringify_ref_value(param_value.get("Value", "")),
            })
        return params

    def _parse_application_settings(self, qbl_data: Dict[str, Any]) -> list:
        settings = []
        resources = qbl_data.get("Resources", {})
        for app_key, app_value in resources.items():
            if not isinstance(app_value, dict) or app_value.get("Type") != "QB::Application":
                continue
            props = SafeExtractor.get_dict(app_value, "Properties")
            settings.append({
                "App Logical ID": app_key,
                "App Name": props.get("Name", ""),
                "Manager": props.get("Manager", ""),
                "App Icon": props.get("AppIcon", ""),
                "App Color": props.get("AppColor", ""),
                "Currency Symbol": props.get("CurrencySymbol", ""),
                "TableV3 State": props.get("TableV3State", ""),
                "TableV3 User Toggle State": props.get("TableV3UserToggleState", ""),
                "Table Order": ", ".join(self._stringify_table_order(props.get("TableOrder", []))),
                "Cross Application Access": self._format_cross_application_access(props.get("CrossApplicationAccess", {})),
            })
        return settings

    def _parse_application_variables(self, qbl_data: Dict[str, Any]) -> list:
        variables = []
        resources = qbl_data.get("Resources", {})
        for app_key, app_value in resources.items():
            if not isinstance(app_value, dict) or app_value.get("Type") != "QB::Application":
                continue
            vars_block = app_value.get("Variables", {})
            for var_key, var_value in vars_block.items():
                if not isinstance(var_value, dict):
                    continue
                var_props = SafeExtractor.get_dict(var_value, "Properties")
                variables.append({
                    "App Logical ID": app_key,
                    "Variable Logical ID": var_key,
                    "Type": var_value.get("Type", ""),
                    "Name": var_props.get("Name", ""),
                    "Value": self._stringify_ref_value(var_props.get("Value", "")),
                })
        return variables

    def _parse_external_resources(self, qbl_data: Dict[str, Any]):
        resources_data = []
        recordsets_data = []
        columns_data = []

        external_resources = qbl_data.get("ExternalResources", {})
        for res_key, res_value in external_resources.items():
            if not isinstance(res_value, dict):
                continue

            props = SafeExtractor.get_dict(res_value, "Properties")
            record_sets = res_value.get("RecordSets", {})

            resources_data.append({
                "Resource Logical ID": res_key,
                "Type": res_value.get("Type", ""),
                "Owner": props.get("Owner", ""),
                "Connection Id": self._stringify_ref_value(props.get("ConnectionId", "")),
                "Is Placeholder": props.get("IsPlaceholder", False),
                "Record Set Count": len(record_sets),
                "Record Set Logical IDs": ", ".join(record_sets.keys()),
            })

            for record_key, record_value in record_sets.items():
                if not isinstance(record_value, dict):
                    continue

                record_props = SafeExtractor.get_dict(record_value, "Properties")
                columns = record_value.get("Columns", {})

                recordsets_data.append({
                    "Resource Logical ID": res_key,
                    "Record Set Logical ID": record_key,
                    "Type": record_value.get("Type", ""),
                    "Set Type": record_props.get("SetType", ""),
                    "External Set ID": self._stringify_ref_value(record_props.get("ExternalSetId", "")),
                    "Column Count": len(columns),
                })

                for column_key, column_value in columns.items():
                    if not isinstance(column_value, dict):
                        continue

                    columns_data.append({
                        "Resource Logical ID": res_key,
                        "Record Set Logical ID": record_key,
                        "Column Logical ID": column_key,
                        "Column Type": column_value.get("Type", ""),
                        "Column ID": column_value.get("Id", ""),
                    })

        return resources_data, recordsets_data, columns_data

    def _find_duplicate_reports(self, parsed_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect reports that share identical field selections and filter criteria."""
        reports = parsed_data.get("reports") or []
        field_matrix = parsed_data.get("report_field_matrix") or []
        if not reports or not field_matrix:
            return []

        report_lookup = {
            report.get("Report Logical ID"): report
            for report in reports
            if report.get("Report Logical ID")
        }
        if not report_lookup:
            return []

        report_field_ids = defaultdict(set)
        report_field_labels = defaultdict(dict)

        for row in field_matrix:
            report_id = row.get("Report Logical ID")
            if not report_id or report_id not in report_lookup:
                continue

            field_identifier = row.get("Field ID") or row.get("Field Logical ID")
            if not field_identifier:
                continue

            field_identifier = str(field_identifier)
            report_field_ids[report_id].add(field_identifier)

            label = row.get("Field Label")
            if label:
                display_value = f"{label} ({field_identifier})" if label != field_identifier else label
            else:
                display_value = field_identifier
            report_field_labels[report_id][field_identifier] = display_value

        if not report_field_ids:
            return []

        def normalize_filters(value):
            if value is None:
                return ""
            if isinstance(value, str):
                return value.strip()
            try:
                return json.dumps(value, sort_keys=True)
            except TypeError:
                return str(value)

        signature_groups = defaultdict(list)
        for report_id, report in report_lookup.items():
            fields = tuple(sorted(report_field_ids.get(report_id, [])))
            if not fields:
                continue

            filter_signature = normalize_filters(report.get("Filters"))
            table_signature = report.get("Table Logical ID") or ""
            app_signature = report.get("App Logical ID") or ""
            signature = (app_signature, table_signature, filter_signature, fields)
            signature_groups[signature].append(report_id)

        duplicates = []
        group_index = 1

        for signature, grouped_reports in signature_groups.items():
            if len(grouped_reports) < 2:
                continue

            app_logical_id = signature[0]
            field_ids = signature[3]
            field_count = len(field_ids)
            field_id_string = ", ".join(field_ids)

            display_fields = []
            for field_id in field_ids:
                display_label = None
                for report_id in grouped_reports:
                    display_label = report_field_labels[report_id].get(field_id)
                    if display_label:
                        break
                display_fields.append(display_label or field_id)
            field_label_string = ", ".join(display_fields)

            for report_id in grouped_reports:
                report = report_lookup[report_id]
                duplicates.append({
                    "Duplicate Group": group_index,
                    "Duplicate Count": len(grouped_reports),
                    "App Logical ID": app_logical_id,
                    "Table Logical ID": report.get("Table Logical ID", ""),
                    "Table Name": self._text_or_blank(report.get("Table Name", "")),
                    "Table ID": self._text_or_blank(report.get("Table ID", "")),
                    "Report Logical ID": report_id,
                    "Report ID": self._text_or_blank(report.get("Report ID", "")),
                    "Report Name": self._text_or_blank(report.get("Report Name", "")),
                    "Report Type": self._text_or_blank(report.get("Type", "")),
                    "Filter Signature": signature[2],
                    "Field Count": field_count,
                    "Field IDs": field_id_string,
                    "Field Labels": field_label_string,
                })

            group_index += 1

        duplicates.sort(
            key=lambda row: (row["Duplicate Group"], self._text_or_blank(row.get("Report Name")))
        )
        return duplicates

    @staticmethod
    def _text_or_blank(value):
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return str(value)

    def _stringify_table_order(self, table_order):
        rows = []
        if isinstance(table_order, list):
            for entry in table_order:
                if isinstance(entry, dict):
                    rows.append(entry.get("Table", ""))
                else:
                    rows.append(str(entry))
        return [row for row in rows if row]

    def _format_cross_application_access(self, access_dict):
        if not isinstance(access_dict, dict):
            return ""
        parts = []
        for realm, ref in access_dict.items():
            role = ""
            if isinstance(ref, dict):
                role = ref.get("Role", "")
            parts.append(f"{realm}: {role}")
        return "; ".join(parts)

    def _stringify_ref_value(self, value):
        if isinstance(value, dict):
            if "Name" in value and len(value) == 1:
                return value["Name"]
            if "Field" in value and len(value) == 1:
                return value["Field"]
            if "Table" in value and len(value) == 1:
                return value["Table"]
            try:
                return json.dumps(value)
            except Exception:
                return str(value)
        if isinstance(value, list):
            return ", ".join(self._stringify_ref_value(v) for v in value)
        if value is None:
            return ""
        return value
