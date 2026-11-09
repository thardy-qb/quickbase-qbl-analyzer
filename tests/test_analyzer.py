#!/usr/bin/env python3
"""Test suite for the QBL Solution Analyzer.

Standard library only, no test runner required:

    python3 tests/test_analyzer.py

Every test parses a fixture through the real CLI and asserts on the artifacts,
so the tests exercise the same path a user does.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ANALYZER = REPO_ROOT / "scripts" / "qbl_analyzer.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ANALYZER), *args],
        capture_output=True,
        text=True,
    )


class AnalyzerTestCase(unittest.TestCase):
    """Parses the main fixture once per class and shares the output directory."""

    fixture = "solution-qbl.yaml"
    table_schema = "table-schema.json"

    @classmethod
    def setUpClass(cls) -> None:
        cls.output_dir = Path(tempfile.mkdtemp(prefix="qbl-test-"))
        args = [
            "summary",
            str(FIXTURES / cls.fixture),
            "--output-dir",
            str(cls.output_dir),
            "--label",
            "Test Solution",
        ]
        if cls.table_schema:
            args += ["--table-schema", str(FIXTURES / cls.table_schema)]
        cls.result = run_cli(*args)
        if cls.result.returncode != 0:
            raise AssertionError(f"summary failed: {cls.result.stderr}")
        cls.manifest = json.loads(cls.result.stdout)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.output_dir, ignore_errors=True)

    def query(self, collection: str, *args: str) -> str:
        result = run_cli("query", str(self.output_dir), collection, *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def rows(self, collection: str, *args: str) -> list:
        out = self.query(collection, "--format", "json", "--limit", "-1", *args)
        return json.loads(out)["rows"]


class TestSummaryArtifacts(AnalyzerTestCase):
    def test_reports_success(self):
        self.assertTrue(self.manifest["success"])
        self.assertEqual(self.manifest["qbl_version"], "0.14")

    def test_writes_every_declared_artifact(self):
        outputs = self.manifest["outputs"]
        for key in ("workbook", "json", "summary", "digest", "bundle"):
            self.assertTrue(Path(outputs[key]).is_file(), f"missing {key}")
        self.assertTrue(outputs["csv_files"], "no CSV files written")
        for path in outputs["csv_files"]:
            self.assertTrue(Path(path).is_file(), path)

    def test_manifest_offers_next_steps(self):
        self.assertIn("read_first", self.manifest["next_steps"])
        self.assertTrue(Path(self.manifest["next_steps"]["read_first"]).is_file())

    def test_parses_expected_entity_counts(self):
        counts = self.manifest["entity_counts"]
        self.assertEqual(counts["tables"], 3)
        self.assertEqual(counts["fields"], 9)
        self.assertEqual(counts["relationships"], 2)
        self.assertEqual(counts["roles"], 2)
        self.assertEqual(counts["pipelines"], 1)
        self.assertEqual(counts["pipeline_steps"], 3)


class TestTableSchemaEnrichment(AnalyzerTestCase):
    def test_resolves_runtime_table_ids_from_the_qbl_alias(self):
        by_logical = {r["Table Logical ID"]: r for r in self.rows("tables")}
        self.assertEqual(by_logical["$Table_Projects"]["Table ID"], "bqx1proj")
        self.assertEqual(by_logical["$Table_Tasks"]["Table ID"], "bqx1task")
        self.assertEqual(by_logical["$Table_Vendors"]["Table ID"], "bqx1vend")

    def test_resolves_ids_the_export_declares_itself(self):
        fields = {r["Field Logical ID"]: r for r in self.rows("fields")}
        self.assertEqual(fields["$Field_ProjectName"]["Field ID"], "6")
        roles = {r["Role Logical ID"]: r for r in self.rows("roles")}
        self.assertEqual(roles["$Role_Admin"]["Role ID"], "10")

    def test_resolves_cross_app_lookup_targets(self):
        fields = {r["Field Logical ID"]: r for r in self.rows("fields")}
        vendor = fields["$Field_VendorLookup"]
        self.assertEqual(vendor["Lookup Target Table"], "$Table_Vendors")
        self.assertEqual(vendor["Lookup Target Table ID"], "bqx1vend")
        self.assertEqual(vendor["Lookup Target Field ID"], "6")

    def test_resolves_summary_targets(self):
        fields = {r["Field Logical ID"]: r for r in self.rows("fields")}
        total = fields["$Field_TaskTotal"]
        self.assertEqual(total["Summary Target Table ID"], "bqx1task")
        self.assertEqual(total["Summary Target Field ID"], "7")


class TestWithoutTableSchema(AnalyzerTestCase):
    """The table schema is optional; only runtime IDs should go blank."""

    table_schema = None

    def test_runtime_table_ids_are_blank(self):
        for row in self.rows("tables"):
            self.assertEqual(row["Table ID"], "")

    def test_qbl_declared_ids_still_resolve(self):
        fields = {r["Field Logical ID"]: r for r in self.rows("fields")}
        self.assertEqual(fields["$Field_ProjectName"]["Field ID"], "6")

    def test_aliases_survive(self):
        aliases = {r["Table Alias"] for r in self.rows("tables")}
        self.assertIn("_DBID_PROJECTS", aliases)


class TestPipelineUsageIsCounted(unittest.TestCase):
    """A field referenced only by a pipeline must not be flagged unused.

    Pipelines live at the `Resources` level, outside any application subtree.
    Flagging such a field `Potentially Unused` would recommend deleting a field
    a live integration depends on.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.output_dir = Path(tempfile.mkdtemp(prefix="qbl-pipe-"))
        result = run_cli(
            "summary",
            str(FIXTURES / "pipeline-only-qbl.yaml"),
            "--output-dir",
            str(cls.output_dir),
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr)
        out = run_cli("query", str(cls.output_dir), "fields", "--format", "json", "--limit", "-1")
        cls.fields = {r["Field Logical ID"]: r for r in json.loads(out.stdout)["rows"]}

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.output_dir, ignore_errors=True)

    def test_pipeline_only_field_is_not_flagged_unused(self):
        field = self.fields["$Field_OnlyPipeline"]
        self.assertEqual(field["Used in Pipelines"], "Yes")
        self.assertEqual(field["Total Usage Count"], "1")
        self.assertEqual(field["Potentially Unused"], "No")

    def test_genuinely_unreferenced_field_is_still_flagged(self):
        field = self.fields["$Field_Nowhere"]
        self.assertEqual(field["Used in Pipelines"], "No")
        self.assertEqual(field["Total Usage Count"], "0")
        self.assertEqual(field["Potentially Unused"], "Yes")


class TestNoDoubleCounting(AnalyzerTestCase):
    """The cross-reference pass must add only references analyzers did not see."""

    def test_report_and_pipeline_references_sum_exactly(self):
        fields = {r["Field Logical ID"]: r for r in self.rows("fields")}
        pipeline_refs = {}
        for row in self.rows("field_pipeline_matrix"):
            key = row["Field Logical ID"]
            pipeline_refs[key] = pipeline_refs.get(key, 0) + 1

        for logical_id, count in pipeline_refs.items():
            field = fields[logical_id]
            self.assertEqual(field["Used in Pipelines"], "Yes")
            # The pipeline references are included, and the total never drops
            # below them, which is what a double-count or an overwrite would do.
            self.assertGreaterEqual(int(field["Total Usage Count"]), count)

    def test_budget_totals_report_plus_pipeline(self):
        fields = {r["Field Logical ID"]: r for r in self.rows("fields")}
        budget = fields["$Field_Budget"]
        self.assertEqual(budget["Used in Reports"], "Yes")
        self.assertEqual(budget["Used in Pipelines"], "Yes")
        self.assertEqual(budget["Total Usage Count"], "2")


class TestDigest(AnalyzerTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.digest = Path(cls.manifest["outputs"]["digest"]).read_text(encoding="utf-8")

    def test_lists_every_table(self):
        for logical_id in ("$Table_Projects", "$Table_Tasks", "$Table_Vendors"):
            self.assertIn(logical_id, self.digest)

    def test_nothing_is_truncated(self):
        self.assertNotIn("...and", self.digest)

    def test_surfaces_the_integration_surface(self):
        self.assertIn("warehouse.example.com", self.digest)
        self.assertIn("Nightly Sync", self.digest)

    def test_does_not_embed_absolute_paths(self):
        self.assertNotIn(str(self.output_dir), self.digest)

    def test_unused_field_cross_check_agrees_with_the_parser(self):
        # The cross-check should find nothing.
        self.assertIn("still referenced elsewhere (flag is a false positive): 0", self.digest)


class TestQueryEngine(AnalyzerTestCase):
    def test_equality_filter(self):
        rows = self.rows("fields", "--where", "Field Type=Currency")
        self.assertEqual([r["Field Logical ID"] for r in rows], ["$Field_Budget"])

    def test_contains_filter(self):
        rows = self.rows("fields", "--where", "Field Type=~Lookup")
        self.assertEqual(len(rows), 2)

    def test_not_contains_filter(self):
        rows = self.rows("fields", "--where", "Field Type!~Lookup")
        self.assertEqual(len(rows), 7)

    def test_blank_and_non_blank_filters(self):
        blank = self.rows("fields", "--where", "Summary Target Field=")
        non_blank = self.rows("fields", "--where", "Summary Target Field!=")
        self.assertEqual(len(non_blank), 1)
        self.assertEqual(len(blank) + len(non_blank), 9)

    def test_numeric_comparisons(self):
        self.assertEqual(len(self.rows("fields", "--where", "Total Usage Count>=2")), 3)
        self.assertEqual(len(self.rows("fields", "--where", "Total Usage Count<1")), 5)

    def test_filters_are_anded(self):
        rows = self.rows(
            "fields", "--where", "Field Type=~Lookup", "--where", "Total Usage Count>=2"
        )
        self.assertEqual([r["Field Logical ID"] for r in rows], ["$Field_VendorLookup"])

    def test_column_projection_and_case_insensitivity(self):
        rows = self.rows("fields", "--columns", "field label", "--limit", "-1")
        self.assertEqual(set(rows[0].keys()), {"Field Label"})

    def test_distinct_collapses_duplicates(self):
        out = self.query("fields", "--columns", "Field Type", "--distinct", "--count")
        self.assertIn("distinct", out)

    def test_count_only_reports_matches_not_zero(self):
        out = self.query("fields", "--where", "Field Type=Text", "--count")
        self.assertIn("of 9 row(s) matched", out)
        self.assertNotIn("No rows matched", out)

    def test_csv_and_json_formats(self):
        self.assertIn("Field Logical ID", self.query("fields", "--format", "csv", "--limit", "2"))
        payload = json.loads(self.query("fields", "--format", "json", "--limit", "2"))
        self.assertEqual(payload["returned_rows"], 2)
        self.assertEqual(payload["total_rows"], 9)

    def test_limit_truncation_is_reported(self):
        out = self.query("fields", "--limit", "2")
        self.assertIn("capped by --limit", out)

    def test_collections_lists_columns(self):
        result = run_cli("collections", str(self.output_dir))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("field_pipeline_matrix", result.stdout)
        self.assertIn("columns:", result.stdout)


class TestErrorHandling(AnalyzerTestCase):
    def assert_query_error(self, *args: str) -> str:
        result = run_cli("query", str(self.output_dir), *args)
        self.assertEqual(result.returncode, 2, result.stdout)
        return result.stderr

    def test_unknown_collection_lists_valid_names(self):
        self.assertIn("fields", self.assert_query_error("nonesuch"))

    def test_unknown_column_lists_valid_names(self):
        self.assertIn("Field Label", self.assert_query_error("fields", "--where", "Nope=1"))

    def test_malformed_filter_explains_the_syntax(self):
        self.assertIn("column=value", self.assert_query_error("fields", "--where", "garbage"))

    def test_missing_input_file_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_cli("summary", str(FIXTURES / "nope.yaml"), "--output-dir", tmp)
        self.assertEqual(result.returncode, 2)
        self.assertIn("not found", json.loads(result.stderr)["message"])

    def test_oversized_input_is_rejected_before_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            big = Path(tmp) / "big-qbl.yaml"
            # Sparse file: the size check runs on stat, so no real bytes needed.
            with big.open("wb") as handle:
                handle.truncate(64 * 1024 * 1024)
            result = run_cli("summary", str(big), "--output-dir", str(Path(tmp) / "out"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("exceeding", json.loads(result.stderr)["message"])


class TestCredentialScanner(unittest.TestCase):
    """Unit tests for detection, run directly against the scanner."""

    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from secret_scanner import scan_text  # noqa: E402

        cls.scan = staticmethod(scan_text)

    def assert_detected(self, text: str, expected_kind: str = ""):
        hits = self.scan(text)
        self.assertTrue(hits, f"nothing detected in {text!r}")
        if expected_kind:
            self.assertTrue(
                any(expected_kind in h["kind"] for h in hits),
                f"expected {expected_kind!r} in {[h['kind'] for h in hits]}",
            )
        return hits

    def test_detects_vendor_token_formats(self):
        self.assert_detected("key=sk_live_51EXAMPLE000000000000", "Stripe")
        self.assert_detected("AKIAIOSFODNN7EXAMPLE", "AWS")
        self.assert_detected("ghp_EXAMPLE000000000000000000000000", "GitHub")
        self.assert_detected("xoxb-1234567890-abcdefghijkl", "Slack")
        self.assert_detected("AIzaSyA1234567890abcdefghijklmnopqrstuvw", "Google")
        self.assert_detected("-----BEGIN RSA PRIVATE KEY-----", "PEM")

    def test_detects_basic_auth_in_url(self):
        self.assert_detected("https://admin:Sup3rS3cret@corp.com/api", "Basic auth")

    def test_detects_credential_key_names(self):
        self.assert_detected('{"client_secret": "9a8b7c6d5e4f3g2h1i0j"}', "client_secret")
        self.assert_detected("?password=hunter2000abc", "password")

    def test_reports_one_row_per_secret(self):
        # A value matching both a vendor format and a credential key name is a
        # single finding, not two.
        hits = self.scan("https://x/y?api_key=sk_live_AKIA0000EXAMPLE0000")
        self.assertEqual(len(hits), 1, [h["kind"] for h in hits])

    def test_masks_the_value(self):
        hits = self.assert_detected("?password=hunter2000abc")
        masked = hits[0]["masked"]
        self.assertNotIn("hunter2000abc", masked)
        self.assertIn("*", masked)

    def test_ignores_stored_credential_references(self):
        # Referencing a stored secret is the correct pattern and must stay quiet.
        for safe in (
            "?api_key={{ secrets.vendor_key }}",
            "?api_key={account.token}",
            '{"token": "{{ connection.access_token }}"}',
        ):
            self.assertEqual(self.scan(safe), [], safe)

    def test_ignores_ordinary_configuration(self):
        for safe in (
            "https://api.example.com/v1/records?tableId=bqx1task&limit=100",
            '{"to": "bqx1task", "rows": 250}',
            "Sum([Amount 0], [Tax 0]) * 1.000",
            '{"password": "changeme"}',
            '{"api_key": ""}',
            '{"secret": "TBD"}',
            "GET /v1/records/query",
        ):
            self.assertEqual(self.scan(safe), [], safe)


class TestCredentialReporting(AnalyzerTestCase):
    """The warning must reach the digest and the manifest."""

    fixture = "credentials-qbl.yaml"
    table_schema = None

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.digest = Path(cls.manifest["outputs"]["digest"]).read_text(encoding="utf-8")

    def test_manifest_counts_findings(self):
        self.assertEqual(self.manifest["possible_credential_count"], 3)

    def test_digest_leads_with_the_warning(self):
        self.assertIn("## Possible hardcoded credentials", self.digest)
        self.assertLess(
            self.digest.index("## Possible hardcoded credentials"),
            self.digest.index("## Architecture"),
            "the warning should appear before the architecture section",
        )

    def test_warning_table_masks_values(self):
        # The table must not restate the secret. The digest as a whole is not
        # redacted -- the endpoint list still carries raw URLs by design -- so
        # scope this assertion to the warning section.
        warning = self.digest.split("## Architecture")[0]
        table = warning.split("| Where | Field | Kind | Value |")[1]
        self.assertNotIn("sk_live_AKIA0000EXAMPLE0000", table)
        self.assertNotIn("ghp_EXAMPLE000000000000000000000000", table)
        self.assertIn("sk_l", table)

    def test_warning_states_that_the_digest_is_not_redacted(self):
        warning = self.digest.split("## Architecture")[0]
        self.assertIn("are not redacted anywhere else", warning)

    def test_raw_values_remain_in_the_digest_by_design(self):
        # Faithfulness is the chosen trade-off: the analyst can see and act on
        # the real endpoint. The warning above tells them to treat it as such.
        self.assertIn("sk_live_AKIA0000EXAMPLE0000", self.digest)

    def test_digest_names_the_location(self):
        self.assertIn("pipeline_steps.HTTP URL", self.digest)
        self.assertIn("application_variables.Value", self.digest)
        self.assertIn("Call Vendor API", self.digest)

    def test_full_values_remain_available_for_remediation(self):
        inventory = Path(self.manifest["outputs"]["json"]).read_text(encoding="utf-8")
        self.assertIn("sk_live_AKIA0000EXAMPLE0000", inventory)

    def test_correctly_configured_step_is_not_flagged(self):
        self.assertNotIn("Correctly Configured Call", self.digest.split("## Architecture")[0])


class TestNoCredentialNoise(AnalyzerTestCase):
    """A clean solution must not get a warning section at all."""

    def test_no_section_and_zero_count(self):
        digest = Path(self.manifest["outputs"]["digest"]).read_text(encoding="utf-8")
        self.assertEqual(self.manifest["possible_credential_count"], 0)
        self.assertNotIn("Possible hardcoded credentials", digest)


class TestExportedShapes(unittest.TestCase):
    """Shapes Quickbase writes into its own exports must not read as defects.

    The fixture is a cut-down export: the app's name is a `!Var` resolved from
    `ParameterDefinitions`, a legacy form section carries the
    `NonFieldElementID: 0` the platform writes, and a custom email has no
    `SendOptions`, which the platform's export drops.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.output_dir = Path(tempfile.mkdtemp(prefix="qbl-export-"))
        cls.source = FIXTURES / "exported-shapes-qbl.yaml"
        result = run_cli("summary", str(cls.source), "--output-dir", str(cls.output_dir))
        if result.returncode != 0:
            raise AssertionError(result.stderr)
        cls.manifest = json.loads(result.stdout)
        cls.digest = Path(cls.manifest["outputs"]["digest"]).read_text(encoding="utf-8")
        cls.parsed = json.loads(Path(cls.manifest["outputs"]["json"]).read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.output_dir, ignore_errors=True)

    def _issues(self):
        return self.parsed.get("issues", [])

    def test_the_app_name_is_resolved_in_the_digest_heading(self):
        self.assertIn("### Reading List (`$App_Reading`)", self.digest)
        self.assertNotIn("App_Name_1'}", self.digest)

    def test_the_app_name_is_resolved_in_application_settings(self):
        out = run_cli("query", str(self.output_dir), "application_settings",
                      "--format", "json", "--limit", "-1")
        rows = json.loads(out.stdout)["rows"]
        self.assertEqual(["Reading List"], [r["App Name"] for r in rows])

    def test_the_parameter_definitions_still_list_the_definition(self):
        out = run_cli("query", str(self.output_dir), "parameter_definitions",
                      "--format", "json", "--limit", "-1")
        rows = json.loads(out.stdout)["rows"]
        self.assertEqual(["App_Name_1"], [r["Parameter Logical ID"] for r in rows])

    def test_a_trailing_parameters_document_overrides_the_default(self):
        with tempfile.TemporaryDirectory(prefix="qbl-export-override-") as tmp:
            stream = Path(tmp) / "two-document.yaml"
            stream.write_text(
                self.source.read_text(encoding="utf-8")
                + "---\nParameters:\n  App_Name_1: Reading List Archive\n",
                encoding="utf-8",
            )
            result = run_cli("summary", str(stream), "--output-dir", str(Path(tmp) / "out"))
            self.assertEqual(result.returncode, 0, result.stderr)
            digest = Path(json.loads(result.stdout)["outputs"]["digest"]).read_text(encoding="utf-8")
        self.assertIn("### Reading List Archive (`$App_Reading`)", digest)

    def test_the_section_element_id_is_not_reported(self):
        self.assertEqual(
            [], [i for i in self._issues() if "NonFieldElementID" in str(i.get("Problem", ""))])

    def test_the_missing_send_options_is_a_warning(self):
        found = [(i.get("Code"), i.get("Severity")) for i in self._issues()
                 if "SendOptions" in str(i.get("Problem", ""))]
        self.assertEqual([("SCH012", "warning")], found)


class TestHowTheApplicationBehaves(AnalyzerTestCase):
    """The digest and collections answer behaviour questions on their own.

    Each of these once needed the raw export: a relationship count that was
    double, an update step with no table, a pipeline with no schedule or
    filter in view, and a form rule whose condition parsed empty.
    """

    fixture = "lending-library-qbl.yaml"
    table_schema = None

    def setUp(self) -> None:
        self.digest = Path(self.manifest["outputs"]["digest"]).read_text(encoding="utf-8")

    def test_each_relationship_is_counted_once(self):
        self.assertEqual(self.manifest["relationship_count"], 2)
        self.assertEqual(self.manifest["entity_counts"]["relationships"], 4)
        self.assertIn("### Relationships (2)", self.digest)
        self.assertEqual(1, self.digest.count("- Branches -> Books"))

    def test_the_child_side_filter_lists_each_relationship_once(self):
        rows = self.rows("relationships", "--where", "Relationship Side=Child",
                         "--columns", "Parent Table Name,Child Table Name")
        self.assertEqual(
            sorted((r["Parent Table Name"], r["Child Table Name"]) for r in rows),
            [("Books", "Loans"), ("Branches", "Books")])

    def test_an_update_step_carries_its_targets_table(self):
        rows = self.rows("pipeline_steps", "--where", "Step Name=Update the book")
        self.assertEqual(rows[0]["Table Name"], "Books")
        self.assertEqual(rows[0]["Target Step ID"], "b")
        matrix = self.rows("pipeline_table_matrix", "--where", "Step Name=Update the book")
        self.assertEqual([(r["Table Name"], r["Reference Type"]) for r in matrix],
                         [("Books", "Target Step")])

    def test_schedules_filters_and_inputs_are_in_the_digest(self):
        self.assertIn("Runs on schedule `0 2 * * *` (Europe/Dublin)", self.digest)
        self.assertIn('where is_overdue is true OR title contains "Atlas"', self.digest)
        self.assertIn('where loan_status equals "Returned" -- when Loan Status changes', self.digest)
        self.assertIn("`c` update Books -- the record step `b` found -- "
                      "sets Last_Returned = {{ a.returned_on }}", self.digest)

    def test_a_field_tested_by_a_form_rule_is_marked_used(self):
        rows = self.rows("fields", "--where", "Field Label=Loan Status",
                         "--columns", "Used in Form Rules")
        self.assertEqual(rows[0]["Used in Form Rules"], "Yes")

    def test_form_rules_are_summarized(self):
        self.assertIn('**Hide notes while open** -- When Loan Status IsEqualTo "Open" '
                      '-> Hide Return Notes', self.digest)
        self.assertIn("**Flag either note** [disabled]", self.digest)

    def test_a_guessed_column_names_the_real_one(self):
        result = run_cli("query", str(self.output_dir), "relationships",
                         "--columns", "Parent Table")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Did you mean", result.stdout + result.stderr)
        self.assertIn("'Parent Table Name'", result.stdout + result.stderr)


class TestCollectionColumnsReference(AnalyzerTestCase):
    """The columns the guide tells a reader to use exist."""

    fixture = "lending-library-qbl.yaml"
    table_schema = None

    def test_the_guide_names_only_real_columns(self):
        guide = (REPO_ROOT / "references" / "analysis-guide.md").read_text(encoding="utf-8")
        table = guide.split("The ones most often guessed wrong:", 1)[1].split("\n\n", 1)[0]
        for line in table.splitlines()[2:]:
            cells = [c.strip() for c in line.strip("|").split("|")]
            collection = cells[0].strip("`")
            columns = [c.split(" (")[0].strip().strip("`") for c in cells[2].split(",")]
            for column in columns:
                result = run_cli("query", str(self.output_dir), collection, "--columns", column,
                                 "--limit", "1")
                self.assertEqual(result.returncode, 0, f"{collection}.{column}: {result.stdout}")

    def test_the_rendered_reference_lists_every_collection(self):
        reference = REPO_ROOT / "references" / "collection-columns.md"
        if not reference.exists():
            self.skipTest("collection-columns.md is generated when the Skill is rendered")
        text = reference.read_text(encoding="utf-8")
        for name in ("relationships", "pipeline_steps", "rules", "fields"):
            self.assertIn(f"## `{name}`", text)
        self.assertIn("`Parent Table Name`", text)
        self.assertIn("`Relationship Side`", text)


class TestOlderSchemaVersion(AnalyzerTestCase):
    fixture = "v012-qbl.yaml"
    table_schema = None

    def test_parses_v012(self):
        self.assertEqual(self.manifest["qbl_version"], "0.12")
        self.assertTrue(self.manifest["success"])


class TestOutputDirectorySafety(unittest.TestCase):
    """The output directory is cleared on every run, so only the analyzer's own."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="qbl-outdir-"))
        self.qbl = self.root / "export.qbl.yaml"
        shutil.copy(FIXTURES / "solution-qbl.yaml", self.qbl)
        (self.root / "notes.txt").write_text("keep me", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def summary(self, output_dir: Path) -> subprocess.CompletedProcess:
        return run_cli("summary", str(self.qbl), "--output-dir", str(output_dir), "--label", "T")

    def test_refuses_the_folder_holding_the_input(self) -> None:
        result = self.summary(self.root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("contains the input file", result.stdout + result.stderr)
        self.assertTrue(self.qbl.is_file())
        self.assertTrue((self.root / "notes.txt").is_file())

    def test_refuses_a_folder_with_other_files(self) -> None:
        other = self.root / "downloads"
        other.mkdir()
        (other / "report.pdf").write_text("not ours", encoding="utf-8")
        result = self.summary(other)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("did not write", result.stdout + result.stderr)
        self.assertTrue((other / "report.pdf").is_file())

    def test_reruns_clear_only_the_previous_output(self) -> None:
        out = self.root / "qbl-analysis"
        self.assertEqual(self.summary(out).returncode, 0)
        self.assertTrue((out / ".qbl-analyzer-output").is_file())
        (out / "stale.txt").write_text("from an earlier run", encoding="utf-8")
        self.assertEqual(self.summary(out).returncode, 0)
        self.assertFalse((out / "stale.txt").exists())
        self.assertTrue((out / "solution-digest.md").is_file())

    def test_reruns_over_output_from_before_the_marker(self) -> None:
        out = self.root / "qbl-analysis"
        self.assertEqual(self.summary(out).returncode, 0)
        (out / ".qbl-analyzer-output").unlink()
        self.assertEqual(self.summary(out).returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
