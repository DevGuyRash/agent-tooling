from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "skills" / "excel-workbook-sync" / "scripts" / "excel_workbook_sync.py"
FIXTURE = ROOT / "skills" / "excel-workbook-sync" / "tests" / "fixtures" / "tr_upload_sheet" / "tr_upload_template.xlsm"


def load_module():
    spec = importlib.util.spec_from_file_location("excel_workbook_sync", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ExcelWorkbookGenericAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def test_ooxml_extract_reads_fixture_surface(self) -> None:
        result = self.module.extract_ooxml(FIXTURE)
        table_names = {item["name"] for item in result["tables"]}
        self.assertIn("tbl_invoices", table_names)
        self.assertIn("tbl_invoice_lines", table_names)
        self.assertGreaterEqual(len(result["queries"]), 4)
        self.assertTrue(result["powerQuery"]["dataMashupPresent"])
        self.assertTrue(result["vba"]["present"])

    def test_pull_writes_expected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir)
            result = self.module.pull_workbook(FIXTURE, output_root, engine="ooxml", visible=False)
            self.assertEqual(result["engine"], "ooxml")
            self.assertTrue((output_root / "normalized.json").exists())
            self.assertTrue((output_root / "workbook_structure" / "tables.json").exists())
            self.assertTrue((output_root / "power_query" / "connections.json").exists())
            self.assertTrue((output_root / "power_query" / "data_mashup.xml").exists())
            self.assertTrue((output_root / "power_query" / "queries" / "Matched.pq").exists())
            self.assertTrue((output_root / "power_query" / "query_files.json").exists())
            self.assertTrue((output_root / "vba" / "vbaProject.bin").exists())
            self.assertTrue((output_root / "ooxml-parts" / "xl" / "workbook.xml").exists())

    def test_pull_falls_back_to_ooxml_when_com_extract_times_out(self) -> None:
        original = self.module.extract_com
        self.module.extract_com = lambda *args, **kwargs: {
            "engine": "com",
            "available": False,
            "timedOut": True,
            "timeoutSeconds": 120,
            "workbook": str(FIXTURE),
        }
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                output_root = Path(temp_dir)
                result = self.module.pull_workbook(FIXTURE, output_root, engine="com", visible=False)
                self.assertEqual(result["engine"], "ooxml")
                self.assertEqual(result["comDiagnostics"]["status"], "timed_out")
                self.assertTrue((output_root / "normalized.json").exists())
        finally:
            self.module.extract_com = original

    def test_merge_does_not_override_ooxml_on_com_failure(self) -> None:
        ooxml_result = self.module.extract_ooxml(FIXTURE)
        merged = self.module.merge_ooxml_and_com(
            ooxml_result,
            {
                "engine": "com",
                "available": False,
                "failed": True,
                "error": "extract-com failed",
            },
        )
        self.assertEqual(merged["engine"], "ooxml")
        self.assertEqual(merged["comDiagnostics"]["status"], "failed")
        self.assertGreaterEqual(len(merged["tables"]), 8)

    def test_compare_results_keeps_raw_and_adds_normalized_sections(self) -> None:
        left = {
            "engine": "ooxml",
            "sheets": [{}],
            "tables": [{}],
            "names": [
                {"name": "UserName", "hidden": False, "refersTo": "=Sheet1!$A$1"},
                {"name": "_xlpm.internal_only", "hidden": True, "refersTo": "=#NAME?"},
            ],
            "conditionalFormatting": [],
            "connections": [],
            "queries": [],
            "vba": {"accessible": False, "components": [], "sha256": "abc"},
        }
        right = {
            "engine": "com",
            "sheets": [{}],
            "tables": [{}],
            "names": [
                {"name": "UserName", "hidden": False, "refersTo": "=Sheet1!$A$1"},
            ],
            "conditionalFormatting": [],
            "connections": [],
            "queries": [],
            "vba": {"accessible": False, "components": [], "sha256": None},
        }

        result = self.module.compare_results(left, right)

        self.assertFalse(result["raw"]["match"])
        self.assertEqual(result["raw"]["mismatches"]["nameCount"], [2, 1])
        self.assertTrue(result["normalized"]["match"])
        self.assertEqual(result["normalized"]["diagnostics"]["filteredNames"]["leftCount"], 1)
        self.assertEqual(result["summary"], result["raw"]["summary"])
        self.assertEqual(result["mismatches"], result["raw"]["mismatches"])
        self.assertEqual(result["raw"]["diagnostics"]["vbaHash"]["status"], "unavailable_on_one_side")

    def test_compare_workbook_writes_rich_compare_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir)
            result = self.module.compare_workbook(FIXTURE, output_root, engine="ooxml", visible=False)
            self.assertTrue(result["raw"]["match"])
            self.assertTrue((output_root / "compare.json").exists())

    def test_snapshot_parts_roundtrip_via_repull(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            workbook_copy = temp_root / FIXTURE.name
            shutil.copy2(FIXTURE, workbook_copy)
            baseline = self.module.pull_workbook(workbook_copy, temp_root / "pull", engine="ooxml", visible=False)
            repulled = self.module.pull_workbook(workbook_copy, temp_root / "repull", engine="ooxml", visible=False)
            self.assertEqual(len(baseline["tables"]), len(repulled["tables"]))
            self.assertEqual(len(baseline["names"]), len(repulled["names"]))
            self.assertTrue(repulled["vba"]["present"])

    def test_matrix_audit_writes_summary_for_copied_workbooks(self) -> None:
        original_run_mutation = self.module.run_mutation
        try:
            self.module.run_mutation = lambda *args, **kwargs: {
                "ran": False,
                "skipped": True,
                "reason": "unit-test",
                "scenarios": [{"name": "unit-test-skip", "status": "skipped"}],
            }
            with tempfile.TemporaryDirectory() as temp_dir:
                output_root = Path(temp_dir)
                result = self.module.matrix_audit_workbooks([FIXTURE], output_root, engine="ooxml", visible=False)
                self.assertEqual(len(result["workbooks"]), 1)
                self.assertTrue((Path(result["runRoot"]) / "matrix-summary.json").exists())
                self.assertTrue((Path(result["runRoot"]) / "matrix-summary.md").exists())
                self.assertEqual(result["workbooks"][0]["scenarioCount"], 1)
        finally:
            self.module.run_mutation = original_run_mutation

    @unittest.skipUnless(load_module().excel_available(), "Excel COM not available")
    def test_com_extract_recovers_live_vba_and_queries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir)
            result = self.module.extract_com(FIXTURE, output_root=output_root, visible=False)
            self.assertEqual(result["engine"], "com")
            self.assertGreaterEqual(len(result["queries"]), 4)
            self.assertTrue(result["vba"]["accessible"])
            self.assertGreaterEqual(len(result["vba"]["components"]), 3)
            self.assertTrue((output_root / "macros" / "modules" / "modAPSync.vba").exists())


if __name__ == "__main__":
    unittest.main()
