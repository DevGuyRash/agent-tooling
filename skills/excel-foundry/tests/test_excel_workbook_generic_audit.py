from __future__ import annotations

import base64
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from textwrap import dedent


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "skills" / "excel-foundry" / "scripts" / "excel_workbook_sync.py"


def load_module():
    spec = importlib.util.spec_from_file_location("excel_workbook_sync", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def build_generic_test_workbook(workbook_path: Path) -> None:
    mashup_buffer = BytesIO()
    with zipfile.ZipFile(mashup_buffer, "w", compression=zipfile.ZIP_DEFLATED) as mashup_zip:
        mashup_zip.writestr("[Content_Types].xml", "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'/>")
        mashup_zip.writestr(
            "Formulas/Section1.m",
            dedent(
                """\
                section Section1;
                shared Matched =
                let
                    Source = #table({"Record","Amount"}, {{"INV-001", 10}})
                in
                    Source;
                shared UnMatched =
                let
                    Source = #table({"Record","Amount"}, {{"INV-002", 20}})
                in
                    Source;
                shared DATA_RECORDS =
                let
                    Source = #table({"Record","Amount"}, {{"INV-003", 30}})
                in
                    Source;
                shared DATA_RECORD_LINES =
                let
                    Source = #table({"Record","LineAmount"}, {{"INV-003", 30}})
                in
                    Source;
                """
            ),
        )
    mashup_base64 = base64.b64encode(mashup_buffer.getvalue()).decode("ascii")

    workbook_files = {
        "[Content_Types].xml": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
              <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
              <Default Extension="xml" ContentType="application/xml"/>
              <Default Extension="bin" ContentType="application/vnd.ms-office.vbaProject"/>
              <Override PartName="/xl/workbook.xml" ContentType="application/vnd.ms-excel.sheet.macroEnabled.main+xml"/>
              <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
              <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
              <Override PartName="/xl/tables/table1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.table+xml"/>
              <Override PartName="/xl/tables/table2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.table+xml"/>
              <Override PartName="/xl/connections.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.connections+xml"/>
              <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
              <Override PartName="/customXml/item1.xml" ContentType="application/xml"/>
            </Types>
            """
        ),
        "_rels/.rels": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
            </Relationships>
            """
        ),
        "xl/workbook.xml": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <sheets>
                <sheet name="DATA_RECORDS" sheetId="1" r:id="rId1"/>
                <sheet name="DATA_RECORD_LINES" sheetId="2" r:id="rId2"/>
              </sheets>
              <definedNames>
                <definedName name="RecordAnchor">DATA_RECORDS!$B$2</definedName>
              </definedNames>
            </workbook>
            """
        ),
        "xl/_rels/workbook.xml.rels": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
              <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
            </Relationships>
            """
        ),
        "xl/worksheets/sheet1.xml": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <sheetData>
                <row r="1">
                  <c r="A1" t="s"><v>0</v></c>
                  <c r="B1" t="s"><v>1</v></c>
                </row>
                <row r="2">
                  <c r="A2" t="s"><v>2</v></c>
                  <c r="B2"><v>10</v></c>
                </row>
              </sheetData>
              <tableParts count="1">
                <tablePart r:id="rId1"/>
              </tableParts>
            </worksheet>
            """
        ),
        "xl/worksheets/sheet2.xml": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <sheetData>
                <row r="1">
                  <c r="A1" t="s"><v>3</v></c>
                  <c r="B1" t="s"><v>4</v></c>
                </row>
                <row r="2">
                  <c r="A2" t="s"><v>2</v></c>
                  <c r="B2"><v>10</v></c>
                </row>
              </sheetData>
              <tableParts count="1">
                <tablePart r:id="rId1"/>
              </tableParts>
            </worksheet>
            """
        ),
        "xl/worksheets/_rels/sheet1.xml.rels": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/table" Target="../tables/table1.xml"/>
            </Relationships>
            """
        ),
        "xl/worksheets/_rels/sheet2.xml.rels": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/table" Target="../tables/table2.xml"/>
            </Relationships>
            """
        ),
        "xl/tables/table1.xml": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <table xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" id="1" name="tbl_records" displayName="tbl_records" ref="A1:B2" totalsRowShown="0">
              <autoFilter ref="A1:B2"/>
              <tableColumns count="2">
                <tableColumn id="1" name="Record"/>
                <tableColumn id="2" name="Amount"/>
              </tableColumns>
            </table>
            """
        ),
        "xl/tables/table2.xml": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <table xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" id="2" name="tbl_record_lines" displayName="tbl_record_lines" ref="A1:B2" totalsRowShown="0">
              <autoFilter ref="A1:B2"/>
              <tableColumns count="2">
                <tableColumn id="1" name="Record"/>
                <tableColumn id="2" name="LineAmount"/>
              </tableColumns>
            </table>
            """
        ),
        "xl/connections.xml": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <connections xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <connection id="1" name="Query - Matched" description="Matched query" type="1" background="1"><dbPr connection="Provider=Microsoft.Mashup.OleDb.1;" command="SELECT * FROM [Matched]"/></connection>
              <connection id="2" name="Query - UnMatched" description="UnMatched query" type="1" background="1"><dbPr connection="Provider=Microsoft.Mashup.OleDb.1;" command="SELECT * FROM [UnMatched]"/></connection>
              <connection id="3" name="Query - DATA_RECORDS" description="Records query" type="1" background="1"><dbPr connection="Provider=Microsoft.Mashup.OleDb.1;" command="SELECT * FROM [DATA_RECORDS]"/></connection>
              <connection id="4" name="Query - DATA_RECORD_LINES" description="Lines query" type="1" background="1"><dbPr connection="Provider=Microsoft.Mashup.OleDb.1;" command="SELECT * FROM [DATA_RECORD_LINES]"/></connection>
            </connections>
            """
        ),
        "xl/sharedStrings.xml": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="5" uniqueCount="5">
              <si><t>Record</t></si>
              <si><t>Amount</t></si>
              <si><t>INV-001</t></si>
              <si><t>Record</t></si>
              <si><t>LineAmount</t></si>
            </sst>
            """
        ),
        "customXml/item1.xml": f'<?xml version="1.0" encoding="utf-8"?><DataMashup xmlns="http://schemas.microsoft.com/DataMashup">{mashup_base64}</DataMashup>',
        "xl/vbaProject.bin": b"dummy-vba-project",
    }

    with zipfile.ZipFile(workbook_path, "w", compression=zipfile.ZIP_DEFLATED) as workbook_zip:
        for name, content in workbook_files.items():
            workbook_zip.writestr(name, content)


def create_live_com_audit_workbook(workbook_path: Path) -> None:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        raise AssertionError("Excel COM test prerequisite failed: PowerShell is unavailable")
    path_literal = str(workbook_path.resolve()).replace("'", "''")
    command = dedent(
        f"""
        $excel = $null
        $workbook = $null
        try {{
            $excel = New-Object -ComObject Excel.Application
            $excel.Visible = $false
            $excel.DisplayAlerts = $false
            $workbook = $excel.Workbooks.Add()
            $sheet = $workbook.Worksheets.Item(1)
            $sheet.Name = 'DATA_RECORDS'
            $sheet.Range('A1').Value2 = 'Record'
            $sheet.Range('B1').Value2 = 'Amount'
            $sheet.Range('A2').Value2 = 'INV-001'
            $sheet.Range('B2').Value2 = 10
            $sheet.Range('A3').Value2 = 'INV-002'
            $sheet.Range('B3').Value2 = 20
            $table = $sheet.ListObjects.Add(1, $sheet.Range('A1:B3'), $null, 1)
            $table.Name = 'tbl_records'
            $lines = $workbook.Worksheets.Add()
            $lines.Name = 'DATA_RECORD_LINES'
            $lines.Range('A1').Value2 = 'Record'
            $lines.Range('B1').Value2 = 'LineAmount'
            $lines.Range('A2').Value2 = 'INV-001'
            $lines.Range('B2').Value2 = 10
            $lineTable = $lines.ListObjects.Add(1, $lines.Range('A1:B2'), $null, 1)
            $lineTable.Name = 'tbl_record_lines'
            $workbook.Queries.Add('Matched', 'let Source = #table({{"Record","Amount"}}, {{{{"INV-001", 10}}}}) in Source') | Out-Null
            $workbook.Queries.Add('UnMatched', 'let Source = #table({{"Record","Amount"}}, {{{{"INV-002", 20}}}}) in Source') | Out-Null
            $workbook.Queries.Add('DATA_RECORDS', 'let Source = Excel.CurrentWorkbook(){{[Name="tbl_records"]}}[Content] in Source') | Out-Null
            $workbook.Queries.Add('DATA_RECORD_LINES', 'let Source = Excel.CurrentWorkbook(){{[Name="tbl_record_lines"]}}[Content] in Source') | Out-Null
            try {{
                $project = $workbook.VBProject
                $module = $project.VBComponents.Add(1)
                $module.Name = 'modGeneratedAudit'
                $module.CodeModule.AddFromString("Option Explicit`r`nPublic Function GeneratedAuditValue() As Long`r`n    GeneratedAuditValue = 42`r`nEnd Function")
                $helpers = $project.VBComponents.Add(1)
                $helpers.Name = 'modGeneratedHelpers'
                $helpers.CodeModule.AddFromString("Option Explicit`r`nPublic Sub GeneratedAuditMacro()`r`n    Debug.Print ""Generated audit macro""`r`nEnd Sub")
            }} catch {{
                throw "Excel COM is available, but VBA project object model access is blocked. Enable Trust access to the VBA project object model for this live COM extraction test. $($_.Exception.Message)"
            }}
            $workbook.SaveAs('{path_literal}', 52)
        }} catch {{
            Write-Error $_.Exception.Message
            exit 1
        }} finally {{
            if ($null -ne $workbook) {{
                $workbook.Close($false)
                [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($workbook)
            }}
            if ($null -ne $excel) {{
                $excel.Quit()
                [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
            }}
            [GC]::Collect()
            [GC]::WaitForPendingFinalizers()
        }}
        """
    )
    proc = subprocess.run(
        [powershell, "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=180,
    )
    if proc.returncode != 0:
        raise AssertionError(proc.stdout + proc.stderr)
    if not workbook_path.exists():
        raise AssertionError(f"Excel COM did not create disposable audit workbook: {workbook_path}")


class ExcelWorkbookGenericAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()
        cls.fixture_dir = tempfile.TemporaryDirectory(prefix="excel-foundry-generic-")
        cls.fixture_path = Path(cls.fixture_dir.name) / "generic-test.xlsm"
        build_generic_test_workbook(cls.fixture_path)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture_dir.cleanup()

    def test_ooxml_extract_reads_fixture_surface(self) -> None:
        result = self.module.extract_ooxml(self.fixture_path)
        table_names = {item["name"] for item in result["tables"]}
        self.assertIn("tbl_records", table_names)
        self.assertIn("tbl_record_lines", table_names)
        self.assertGreaterEqual(len(result["queries"]), 4)
        self.assertTrue(result["powerQuery"]["dataMashupPresent"])
        self.assertTrue(result["vba"]["present"])

    def test_package_readable_workbook_recognizes_zip_backed_formats(self) -> None:
        self.assertTrue(self.module.package_readable_workbook(self.fixture_path))
        with tempfile.TemporaryDirectory() as temp_dir:
            legacy = Path(temp_dir) / "legacy.xls"
            legacy.write_bytes(b"not-a-zip")
            binary = Path(temp_dir) / "legacy.xlsb"
            binary.write_bytes(b"not-a-zip")
            self.assertFalse(self.module.package_readable_workbook(legacy))
            self.assertFalse(self.module.package_readable_workbook(binary))

    def test_pull_writes_expected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir)
            result = self.module.pull_workbook(self.fixture_path, output_root, engine="ooxml", visible=False)
            self.assertEqual(result["engine"], "ooxml")
            self.assertTrue((output_root / "normalized.json").exists())
            self.assertTrue((output_root / "workbook_structure" / "sheets.json").exists())
            self.assertTrue((output_root / "workbook_structure" / "tables.json").exists())
            self.assertTrue((output_root / "workbook_structure" / "formulas.json").exists())
            self.assertTrue((output_root / "workbook_structure" / "data_validation.json").exists())
            self.assertTrue((output_root / "workbook_structure" / "protection.json").exists())
            self.assertTrue((output_root / "workbook_structure" / "charts.json").exists())
            self.assertTrue((output_root / "workbook_structure" / "pivots.json").exists())
            self.assertTrue((output_root / "power_query" / "connections.json").exists())
            self.assertTrue((output_root / "power_query" / "data_mashup.xml").exists())
            self.assertTrue((output_root / "power_query" / "queries" / "Matched.pq").exists())
            self.assertTrue((output_root / "power_query" / "query_files.json").exists())
            self.assertTrue((output_root / "vba" / "vbaProject.bin").exists())
            self.assertTrue((output_root / "ooxml-parts" / "xl" / "workbook.xml").exists())
            normalized = self.module.json.loads((output_root / "normalized.json").read_text(encoding="utf-8"))
            self.assertEqual(normalized["nameDiagnostics"]["filteredInternalNameCount"], 0)

    def test_python_cli_pull_defaults_to_summary_stdout_and_writes_full_result_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "pull"
            result_path = Path(temp_dir) / "result.json"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "pull",
                    "--workbook",
                    str(self.fixture_path),
                    "--output-root",
                    str(output_root),
                    "--engine",
                    "ooxml",
                    "--result-path",
                    str(result_path),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=120,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            summary = json.loads(proc.stdout)
            self.assertEqual(summary["command"], "pull")
            self.assertEqual(summary["counts"]["sheets"], 2)
            self.assertTrue(result_path.exists())
            full_payload = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(full_payload["engine"], "ooxml")

    def test_pull_normalized_output_filters_internal_names(self) -> None:
        normalized = self.module.build_pull_normalized_payload(
            {
                "names": [
                    {"name": "RecordAnchor", "hidden": False, "refersTo": "=Sheet1!$B$2"},
                    {"name": "_xlfn.SINGLE", "hidden": True, "refersTo": "=#NAME?"},
                    {"name": "_xlpm.internal_only", "hidden": True, "refersTo": "=#NAME?"},
                ]
            }
        )
        self.assertEqual([item["name"] for item in normalized["names"]], ["RecordAnchor"])
        self.assertEqual(normalized["nameDiagnostics"]["filteredInternalNameCount"], 2)

    def test_package_audit_mutation_adds_defined_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_copy = Path(temp_dir) / self.fixture_path.name
            shutil.copy2(self.fixture_path, workbook_copy)
            package_path = ROOT / "skills" / "excel-foundry" / "scripts" / "excel_workbook_package.py"
            spec = importlib.util.spec_from_file_location("excel_workbook_package", package_path)
            package_module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(package_module)
            report = package_module.apply_audit_mutation(workbook_copy)
            mutated = package_module.build_query_payload(workbook_copy, ["names"])
            self.assertTrue(report["packageFallback"])
            self.assertIn("ExcelSyncAuditMutation", {item["name"] for item in mutated["names"]})

    def test_pull_falls_back_to_ooxml_when_com_extract_times_out(self) -> None:
        original = self.module.extract_com_for_read
        self.module.extract_com_for_read = lambda *args, **kwargs: {
            "engine": "com",
            "available": False,
            "timedOut": True,
            "timeoutSeconds": 120,
            "workbook": str(self.fixture_path),
        }
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                output_root = Path(temp_dir)
                result = self.module.pull_workbook(self.fixture_path, output_root, engine="com", visible=False)
                self.assertEqual(result["engine"], "ooxml")
                self.assertEqual(result["comDiagnostics"]["status"], "timed_out")
                self.assertTrue((output_root / "normalized.json").exists())
        finally:
            self.module.extract_com_for_read = original

    def test_pull_uses_temp_copy_for_com_reads(self) -> None:
        original = self.module.extract_com
        seen_path: Path | None = None

        def fake_extract(path: Path, *args, **kwargs):
            nonlocal seen_path
            seen_path = Path(path)
            return {
                "engine": "com",
                "available": False,
                "timedOut": True,
                "timeoutSeconds": 120,
                "workbook": str(path),
            }

        self.module.extract_com = fake_extract
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                self.module.pull_workbook(self.fixture_path, Path(temp_dir), engine="com", visible=False)
            self.assertIsNotNone(seen_path)
            assert seen_path is not None
            self.assertNotEqual(seen_path.resolve(), self.fixture_path.resolve())
            self.assertEqual(seen_path.suffix, self.fixture_path.suffix)
        finally:
            self.module.extract_com = original

    def test_merge_does_not_override_ooxml_on_com_failure(self) -> None:
        ooxml_result = self.module.extract_ooxml(self.fixture_path)
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
        self.assertEqual(len(merged["tables"]), 2)

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
            "vba": {"accessible": True, "components": [{"name": "Module1"}], "sha256": None},
        }

        result = self.module.compare_results(left, right)

        self.assertTrue(result["comparisonAvailable"])
        self.assertEqual(result["comparisonStatus"], "ok")
        self.assertFalse(result["raw"]["match"])
        self.assertEqual(result["raw"]["mismatches"]["nameCount"], [2, 1])
        self.assertEqual(result["raw"]["mismatches"]["vbaAccessible"], [False, True])
        self.assertTrue(result["normalized"]["match"])
        self.assertEqual(result["normalized"]["diagnostics"]["filteredNames"]["leftCount"], 1)
        self.assertTrue(result["normalized"]["diagnostics"]["liveVba"]["excludedFromParity"])
        self.assertEqual(
            result["normalized"]["diagnostics"]["liveVba"]["mismatches"]["vbaComponentCount"],
            [0, 1],
        )
        self.assertEqual(result["summary"], result["raw"]["summary"])
        self.assertEqual(result["mismatches"], result["raw"]["mismatches"])
        self.assertEqual(result["raw"]["diagnostics"]["vbaHash"]["status"], "unavailable_on_one_side")

    def test_merge_queries_keeps_data_mashup_queries_and_connection_only_queries(self) -> None:
        merged = self.module.merge_queries(
            [
                {
                    "name": "ExcelSyncAuditQuery_Main",
                    "description": "",
                    "formula": "let Source = 1 in Source",
                    "source": "data-mashup",
                }
            ],
            [
                {
                    "name": "Query - Existing Workbook Query",
                    "description": "connection only",
                },
                {
                    "name": "Query - ExcelSyncAuditQuery_Main",
                    "description": "duplicate connection name",
                },
                {
                    "name": "Query - ExcelSyncAuditQuery_Main(1)",
                    "description": "duplicate load name",
                },
            ],
        )

        self.assertEqual(
            [item["name"] for item in merged],
            ["ExcelSyncAuditQuery_Main", "Existing Workbook Query"],
        )
        self.assertEqual(merged[1]["source"], "connection-name")

    def test_render_matrix_summary_uses_delta_status_labels(self) -> None:
        summary = {
            "generatedAt": "2026-04-10T00:00:00+00:00",
            "engine": "com",
            "workbooks": [
                {
                    "workbookName": "sample.xlsx",
                    "baselineComparisonStatus": "ok",
                    "postMutationComparisonStatus": "ok",
                    "baselineRawMatch": False,
                    "baselineNormalizedMatch": True,
                    "deltaMatch": False,
                    "deltaStatus": "changed",
                    "scenarioCount": 9,
                }
            ],
        }

        rendered = self.module.render_matrix_summary(summary)

        self.assertIn("| Workbook | Baseline Status | Post-Mutation Status | Raw Compare | Normalized Compare | Mutation Delta | Scenarios |", rendered)
        self.assertIn("| sample.xlsx | ok | ok | fail | pass | changed | 9 |", rendered)

    def test_render_matrix_summary_uses_na_for_unavailable_compare(self) -> None:
        summary = {
            "generatedAt": "2026-04-10T00:00:00+00:00",
            "engine": "com",
            "workbooks": [
                {
                    "workbookName": "sample.xlsb",
                    "baselineComparisonStatus": "package_unavailable",
                    "postMutationComparisonStatus": "package_unavailable",
                    "baselineRawMatch": None,
                    "baselineNormalizedMatch": None,
                    "deltaMatch": False,
                    "deltaStatus": "changed",
                    "scenarioCount": 3,
                }
            ],
        }

        rendered = self.module.render_matrix_summary(summary)

        self.assertIn("| sample.xlsb | package_unavailable | package_unavailable | n/a | n/a | changed | 3 |", rendered)

    def test_compare_workbook_writes_rich_compare_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir)
            result = self.module.compare_workbook(self.fixture_path, output_root, engine="ooxml", visible=False)
            self.assertTrue(result["raw"]["match"])
            self.assertTrue((output_root / "compare.json").exists())

    def test_compare_workbook_reports_unavailable_when_com_extract_times_out(self) -> None:
        original = self.module.extract_com_for_read
        self.module.extract_com_for_read = lambda *args, **kwargs: {
            "engine": "com",
            "available": False,
            "timedOut": True,
            "timeoutSeconds": 120,
            "workbook": str(self.fixture_path),
        }
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                output_root = Path(temp_dir)
                result = self.module.compare_workbook(self.fixture_path, output_root, engine="com", visible=False)
                self.assertFalse(result["comparisonAvailable"])
                self.assertEqual(result["comparisonStatus"], "com_timed_out")
                self.assertIsNone(result["raw"]["match"])
                self.assertEqual(result["raw"]["mismatches"], {})
                self.assertEqual(result["comDiagnostics"]["timeoutSeconds"], 120)
                self.assertTrue(result["comDiagnostics"]["packageReadable"])
                self.assertEqual(result["comDiagnostics"]["workbookFormat"], ".xlsm")
        finally:
            self.module.extract_com_for_read = original

    def test_compare_workbook_captures_open_attempt_diagnostics_for_com_failures(self) -> None:
        original = self.module.extract_com_for_read
        self.module.extract_com_for_read = lambda *args, **kwargs: {
            "engine": "com",
            "available": False,
            "failed": True,
            "error": "Unable to get the Open property of the Workbooks class",
            "openDiagnostics": {
                "readOnlyIntent": True,
                "attempts": [
                    {"label": "direct-open-readonly-default", "succeeded": False},
                    {"label": "direct-open-readonly-repair", "succeeded": False},
                ],
            },
            "workbook": str(self.fixture_path),
        }
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                output_root = Path(temp_dir)
                result = self.module.compare_workbook(self.fixture_path, output_root, engine="com", visible=False)
                self.assertFalse(result["comparisonAvailable"])
                self.assertEqual(result["comparisonStatus"], "com_open_failed")
                self.assertEqual(result["comDiagnostics"]["openDiagnostics"]["attemptCount"], 2)
                self.assertTrue(result["comDiagnostics"]["openDiagnostics"]["readOnlyIntent"])
        finally:
            self.module.extract_com_for_read = original

    def test_pull_workbook_uses_com_only_for_xlsb(self) -> None:
        original = self.module.extract_com_for_read
        try:
            self.module.extract_com_for_read = lambda *args, **kwargs: {
                "engine": "com",
                "sheets": [{"name": "Sheet1"}],
                "tables": [],
                "tableMappings": [],
                "names": [],
                "conditionalFormatting": [],
                "connections": [],
                "queries": [],
                "powerQuery": {"dataMashupPresent": False, "dataMashupSha256": None, "packageEntries": []},
                "vba": {"present": False, "sha256": None, "size": 0, "accessible": False, "components": [], "references": []},
            }
            with tempfile.TemporaryDirectory() as temp_dir:
                workbook = Path(temp_dir) / "legacy.xlsb"
                workbook.write_bytes(b"legacy-binary")
                output_root = Path(temp_dir) / "out"
                result = self.module.pull_workbook(workbook, output_root, engine="com", visible=False)
                self.assertEqual(result["engine"], "com")
                self.assertFalse((output_root / "ooxml-parts").exists())
                self.assertTrue((output_root / "normalized.json").exists())
        finally:
            self.module.extract_com_for_read = original

    def test_compare_workbook_reports_package_unavailable_for_xlsb(self) -> None:
        original = self.module.extract_com_for_read
        try:
            self.module.extract_com_for_read = lambda *args, **kwargs: {
                "engine": "com",
                "sheets": [{"name": "Sheet1"}],
                "tables": [],
                "tableMappings": [],
                "names": [],
                "conditionalFormatting": [],
                "connections": [],
                "queries": [],
                "powerQuery": {"dataMashupPresent": False, "dataMashupSha256": None, "packageEntries": []},
                "vba": {"present": False, "sha256": None, "size": 0, "accessible": False, "components": [], "references": []},
            }
            with tempfile.TemporaryDirectory() as temp_dir:
                workbook = Path(temp_dir) / "legacy.xlsb"
                workbook.write_bytes(b"legacy-binary")
                output_root = Path(temp_dir) / "out"
                result = self.module.compare_workbook(workbook, output_root, engine="com", visible=False)
                self.assertFalse(result["comparisonAvailable"])
                self.assertEqual(result["comparisonStatus"], "package_unavailable")
                self.assertIsNone(result["match"])
                self.assertEqual(result["leftEngine"], "com")
        finally:
            self.module.extract_com_for_read = original

    def test_snapshot_parts_roundtrip_via_repull(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            workbook_copy = temp_root / self.fixture_path.name
            shutil.copy2(self.fixture_path, workbook_copy)
            baseline = self.module.pull_workbook(workbook_copy, temp_root / "pull", engine="ooxml", visible=False)
            repulled = self.module.pull_workbook(workbook_copy, temp_root / "repull", engine="ooxml", visible=False)
            self.assertEqual(len(baseline["tables"]), len(repulled["tables"]))
            self.assertEqual(len(baseline["names"]), len(repulled["names"]))
            self.assertTrue(repulled["vba"]["present"])

    def test_matrix_audit_writes_summary_for_copied_workbooks(self) -> None:
        original_run_audit_subprocess = self.module.run_audit_subprocess
        try:
            self.module.run_audit_subprocess = lambda *args, **kwargs: {
                "workbook": str(self.fixture_path),
                "matrixStatus": "completed",
                "baselineCompare": {"raw": {"match": True}, "normalized": {"match": True}},
                "postMutationCompare": {"raw": {"match": True}, "normalized": {"match": True}},
                "delta": {"match": True},
                "mutationReport": {"scenarios": [{"name": "unit-test-skip", "status": "skipped"}]},
            }
            with tempfile.TemporaryDirectory() as temp_dir:
                output_root = Path(temp_dir)
                result = self.module.matrix_audit_workbooks([self.fixture_path], output_root, engine="ooxml", visible=False)
                self.assertEqual(len(result["workbooks"]), 1)
                self.assertTrue((Path(result["runRoot"]) / "matrix-summary.json").exists())
                self.assertTrue((Path(result["runRoot"]) / "matrix-summary.md").exists())
                self.assertEqual(result["workbooks"][0]["scenarioCount"], 1)
                self.assertEqual(result["workbooks"][0]["status"], "completed")
                self.assertEqual(result["workbooks"][0]["mutationStatus"], "unchanged")
                self.assertIsNone(result["workbooks"][0]["baselineComparisonStatus"])
                self.assertIsNone(result["workbooks"][0]["postMutationComparisonStatus"])
                self.assertTrue(result["workbooks"][0]["slug"].startswith("01-"))
                self.assertEqual(result["workbooks"][0]["relativeRoot"], result["workbooks"][0]["slug"])
        finally:
            self.module.run_audit_subprocess = original_run_audit_subprocess

    @unittest.skipUnless(load_module().excel_available(), "Excel COM not available")
    def test_com_extract_recovers_live_vba_and_queries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "extract"
            workbook_path = Path(temp_dir) / "live-com-audit.xlsm"
            create_live_com_audit_workbook(workbook_path)
            result = self.module.extract_com(workbook_path, output_root=output_root, visible=False)
            self.assertEqual(result["engine"], "com")
            self.assertGreaterEqual(len(result["queries"]), 4)
            self.assertTrue(result["vba"]["accessible"])
            self.assertGreaterEqual(len(result["vba"]["components"]), 3)
            self.assertTrue((output_root / "macros" / "modules" / "modGeneratedAudit.vba").exists())


if __name__ == "__main__":
    unittest.main()
