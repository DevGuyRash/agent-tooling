import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = ROOT / "skills" / "excel-foundry"
MATRIX_PATH = SKILL_ROOT / "references" / "excel-capability-matrix.json"
LAUNCHER = SKILL_ROOT / "scripts" / "excel-foundry.ps1"


def probe_excel_com(timeout: int = 180) -> tuple[bool, str]:
    if os.name != "nt":
        return False, "Excel COM is only available on Windows"
    command = """
    $excel = $null
    try {
        $excel = New-Object -ComObject Excel.Application
        $excel.Visible = $false
        $excel.DisplayAlerts = $false
        [pscustomobject]@{ available = $true; version = $excel.Version } | ConvertTo-Json -Compress
    }
    catch {
        [pscustomobject]@{ available = $false; error = $_.Exception.Message } | ConvertTo-Json -Compress
        exit 2
    }
    finally {
        if ($null -ne $excel) {
            $excel.DisplayAlerts = $false
            $excel.Quit()
            [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
        }
        [GC]::Collect()
        [GC]::WaitForPendingFinalizers()
    }
    """
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"Excel COM probe failed: {exc}"
    if proc.returncode != 0:
        try:
            return False, f"Excel COM unavailable: {json.loads(proc.stdout).get('error')}"
        except json.JSONDecodeError:
            return False, (proc.stdout + proc.stderr).strip()
    return True, "Excel COM available"


EXCEL_COM_AVAILABLE, EXCEL_COM_REASON = probe_excel_com()


class ExcelFoundryLiveCapabilityMatrixTests(unittest.TestCase):
    maxDiff = 2000

    def setUp(self) -> None:
        self.matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        self.surfaces = self.matrix["surfaces"]
        self.secrets = {
            name: value
            for name, value in os.environ.items()
            if name.startswith("EXCEL_FOUNDRY_") and any(marker in name for marker in ("TOKEN", "SECRET", "PASSWORD", "KEY"))
            and value
        }
        self.tmp = tempfile.TemporaryDirectory(prefix="excel-foundry-live-matrix-")
        self.run_root = Path(self.tmp.name)
        self.workbook = self.run_root / "matrix-live-disposable.xlsx"
        self.desktop_workbook = self.run_root / "matrix-live-desktop.xlsx"
        self.evidence: list[dict[str, Any]] = []
        self.command_cache: dict[tuple[str, ...], dict[str, Any]] = {}
        self.surface_sync_cache: set[str] = set()
        self._create_disposable_workbook()
        if EXCEL_COM_AVAILABLE:
            self._create_disposable_desktop_workbook()

    def tearDown(self) -> None:
        evidence_path = self.run_root / "capability-evidence.json"
        evidence_path.write_text(json.dumps(self.evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self._assert_no_secret_leaks()
        self.tmp.cleanup()

    def test_matrix_operations_are_probed_on_a_disposable_live_workbook(self) -> None:
        visited_surfaces: set[str] = set()
        visited_operations: set[tuple[str, str]] = set()

        for surface in self.surfaces:
            surface_id = surface["id"]
            for operation in surface["operations"]:
                with self.subTest(surface=surface_id, operation=operation):
                    evidence = self._probe_operation(surface, operation)
                    self._assert_standard_evidence(surface, operation, evidence)
                    visited_surfaces.add(surface_id)
                    visited_operations.add((surface_id, operation))
                    if (surface_id, operation) in self._real_package_operations():
                        self.assertEqual(evidence["status"], "executed", evidence)
                        self.assertTrue(evidence["readback"], evidence)

        expected_operations = {
            (surface["id"], operation)
            for surface in self.surfaces
            for operation in surface["operations"]
        }
        self.assertEqual({surface["id"] for surface in self.surfaces}, visited_surfaces)
        self.assertEqual(expected_operations, visited_operations)

    def _create_disposable_workbook(self) -> None:
        payload = self.run_foundry(["workbook", "create", "-WorkbookPath", str(self.workbook)])
        self.assertEqual(payload.get("backend"), "package", payload)
        self.assertTrue(self.workbook.exists())
        self.run_foundry(["sheet", "create", "-WorkbookPath", str(self.workbook), "-Sheet", "Inputs"])
        self.run_foundry(["sheet", "create", "-WorkbookPath", str(self.workbook), "-Sheet", "Scratch"])
        self.run_foundry(["sheet", "create", "-WorkbookPath", str(self.workbook), "-Sheet", "ToDelete"])
        self.run_foundry(["cell", "set", "-WorkbookPath", str(self.workbook), "-Sheet", "Inputs", "-Address", "A1", "-ValueJson", '"Label"'])
        self.run_foundry(["range", "set", "-WorkbookPath", str(self.workbook), "-Sheet", "Inputs", "-RangeRef", "A2:B3", "-ValuesJson", '[[1,2],[3,4]]'])
        self.run_foundry(["name", "set", "-WorkbookPath", str(self.workbook), "-Name", "InitialName", "-RefersTo", "=Inputs!$A$1"])

    def _create_disposable_desktop_workbook(self) -> None:
        command = f"""
        $excel = New-Object -ComObject Excel.Application
        $excel.Visible = $false
        $excel.DisplayAlerts = $false
        $workbook = $excel.Workbooks.Add()
        try {{
            $sheet = $workbook.Worksheets.Item(1)
            $sheet.Name = 'DATA_RECORDS'
            $sheet.Range('A1').Value2 = 'Region'
            $sheet.Range('B1').Value2 = 'Category'
            $sheet.Range('C1').Value2 = 'Amount'
            $sheet.Range('A2').Value2 = 'West'
            $sheet.Range('B2').Value2 = 'Hardware'
            $sheet.Range('C2').Value2 = 10
            $sheet.Range('A3').Value2 = 'East'
            $sheet.Range('B3').Value2 = 'Software'
            $sheet.Range('C3').Value2 = 20
            $table = $sheet.ListObjects.Add(1, $sheet.Range('A1:C3'), $null, 1)
            $table.Name = 'tbl_matrix_live'
            $sheet.Hyperlinks.Add($sheet.Range('E2'), 'https://example.invalid/matrix', '', '', 'Matrix link') | Out-Null
            $sheet.Range('F2').AddComment('Matrix comment') | Out-Null
            $chart = $sheet.Shapes.AddChart2(201, 51, 360, 20, 300, 180).Chart
            $chart.SetSourceData($sheet.Range('A1:C3'))
            $pivotSheet = $workbook.Worksheets.Add()
            $pivotSheet.Name = 'PIVOTS'
            $cache = $workbook.PivotCaches().Create(1, $sheet.Range('A1:C3'))
            $pivot = $cache.CreatePivotTable($pivotSheet.Range('A3'), 'MATRIX_LIVE_PIVOT')
            $pivot.PivotFields('Region').Orientation = 1
            [void]$pivot.AddDataField($pivot.PivotFields('Amount'), 'Total Amount', -4157)
            $workbook.SaveAs('{self.desktop_workbook}', 51)
        }}
        finally {{
            $workbook.Close($false)
            $excel.Quit()
            [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($workbook)
            [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
        }}
        """
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True,
            text=True,
            timeout=180,
        )
        self._assert_no_secret_text(completed.stdout, "stdout")
        self._assert_no_secret_text(completed.stderr, "stderr")
        if completed.returncode != 0:
            self.fail(completed.stdout + completed.stderr)

    def _probe_operation(self, surface: dict[str, Any], operation: str) -> dict[str, Any]:
        surface_id = surface["id"]
        recipe = self._recipe(surface_id, operation)
        if recipe is not None:
            payload = recipe()
            evidence = self._evidence(surface, operation, "executed", payload=payload, readback=True, changed=self._operation_changes(operation))
            self.evidence.append(evidence)
            return evidence

        if self._can_inventory_package_surface(surface):
            payload = self._inventory_package_surface(surface_id)
            evidence = self._evidence(surface, operation, "inventory", payload=payload, readback=True, changed=False)
            self.evidence.append(evidence)
            return evidence

        desktop_recipe = self._desktop_recipe(surface_id, operation)
        if desktop_recipe is not None:
            if EXCEL_COM_AVAILABLE:
                payload = desktop_recipe()
                evidence = self._evidence(surface, operation, "desktop-inventory", payload=payload, readback=True, changed=False)
            else:
                payload = {"backend": "excel", "warnings": [EXCEL_COM_REASON]}
                evidence = self._evidence(surface, operation, "limitation", payload=payload, readback=False, changed=False)
            self.evidence.append(evidence)
            return evidence

        if self._is_cloud_surface(surface):
            payload = {"backend": surface.get("writeLane") or surface.get("readLane") or surface.get("route"), "dryRun": True}
            evidence = self._evidence(surface, operation, "dry-run", payload=payload, readback=False, changed=False)
            self.evidence.append(evidence)
            return evidence

        limitation = self._matrix_limitation(surface, operation)
        evidence = self._evidence(surface, operation, "limitation", payload={"limitation": limitation}, readback=False, changed=False)
        self.evidence.append(evidence)
        return evidence

    def _recipe(self, surface_id: str, operation: str):
        recipes = {
            ("workbook", "create"): lambda: self.run_foundry(["workbook", "inspect", "-WorkbookPath", str(self.workbook)]),
            ("workbook", "get"): lambda: self.run_foundry(["workbook", "inspect", "-WorkbookPath", str(self.workbook)]),
            ("workbook", "inspect"): lambda: self.run_foundry(["workbook", "inspect", "-WorkbookPath", str(self.workbook)]),
            ("sheets", "list"): lambda: self.run_foundry(["sheet", "list", "-WorkbookPath", str(self.workbook)]),
            ("sheets", "get"): lambda: self.run_foundry(["sheet", "list", "-WorkbookPath", str(self.workbook)]),
            ("sheets", "create"): self._create_sheet_and_readback,
            ("sheets", "delete"): self._delete_sheet_and_readback,
            ("sheets", "move"): self._reorder_sheets_and_readback,
            ("cells", "get"): lambda: self.run_foundry(["cell", "get", "-WorkbookPath", str(self.workbook), "-Sheet", "Inputs", "-Address", "A1"]),
            ("cells", "update"): self._set_cell_and_readback,
            ("cells", "clear"): self._clear_cell_and_readback,
            ("ranges", "get"): lambda: self.run_foundry(["range", "get", "-WorkbookPath", str(self.workbook), "-Sheet", "Inputs", "-RangeRef", "A2:B3"]),
            ("ranges", "update"): self._set_range_and_readback,
            ("ranges", "clear"): self._clear_range_and_readback,
            ("names", "list"): lambda: self.run_foundry(["name", "list", "-WorkbookPath", str(self.workbook)]),
            ("names", "get"): lambda: self.run_foundry(["name", "list", "-WorkbookPath", str(self.workbook)]),
            ("names", "create"): self._create_name_and_readback,
            ("names", "update"): self._update_name_and_readback,
            ("names", "delete"): self._delete_name_and_readback,
            ("formulas", "list"): lambda: self.run_foundry(["formula-list", "-WorkbookPath", str(self.workbook)]),
            ("formulas", "get"): lambda: self.run_foundry(["formula-list", "-WorkbookPath", str(self.workbook)]),
            ("data-validation", "list"): lambda: self.run_foundry(["validation-list", "-WorkbookPath", str(self.workbook)]),
            ("data-validation", "get"): lambda: self.run_foundry(["validation-list", "-WorkbookPath", str(self.workbook)]),
            ("cf", "list"): lambda: self.run_foundry(["query", "-WorkbookPath", str(self.workbook), "-Surface", "cf"]),
            ("cf", "get"): lambda: self.run_foundry(["query", "-WorkbookPath", str(self.workbook), "-Surface", "cf"]),
            ("hyperlinks", "list"): lambda: self.run_foundry(["hyperlink-list", "-WorkbookPath", str(self.workbook)]),
            ("hyperlinks", "get"): lambda: self.run_foundry(["hyperlink-list", "-WorkbookPath", str(self.workbook)]),
            ("comments", "list"): lambda: self.run_foundry(["comment-list", "-WorkbookPath", str(self.workbook)]),
            ("comments", "get"): lambda: self.run_foundry(["comment-list", "-WorkbookPath", str(self.workbook)]),
            ("print", "get"): lambda: self.run_foundry(["print-get", "-WorkbookPath", str(self.workbook)]),
            ("print", "inspect"): lambda: self.run_foundry(["print-get", "-WorkbookPath", str(self.workbook)]),
            ("protection", "get"): lambda: self.run_foundry(["protection-get", "-WorkbookPath", str(self.workbook)]),
            ("protection", "inspect"): lambda: self.run_foundry(["protection-get", "-WorkbookPath", str(self.workbook)]),
            ("tables", "list"): lambda: self.run_foundry(["table", "list", "-WorkbookPath", str(self.workbook)]),
            ("tables", "get"): lambda: self.run_foundry(["table", "list", "-WorkbookPath", str(self.workbook)]),
            ("charts", "list"): lambda: self.run_foundry(["query", "-WorkbookPath", str(self.workbook), "-Surface", "charts"]),
            ("charts", "get"): lambda: self.run_foundry(["query", "-WorkbookPath", str(self.workbook), "-Surface", "charts"]),
            ("external-files", "list"): lambda: self.run_foundry(["query", "-WorkbookPath", str(self.workbook), "-Surface", "workbook,connections,pq"]),
            ("external-files", "inspect"): lambda: self.run_foundry(["inspect", "-WorkbookPath", str(self.workbook), "-Surface", "workbook,connections,pq"]),
        }
        return recipes.get((surface_id, operation))

    def _desktop_recipe(self, surface_id: str, operation: str):
        if operation == "export" and surface_id in {"exports", "privacy"}:
            return self._desktop_pdf_export
        commands = {
            "files": lambda: self.run_foundry(["workbook", "inspect", "-WorkbookPath", str(self.desktop_workbook)], timeout=180),
            "chart-sheets": lambda: self.run_foundry(["chart-sheet", "list", "-WorkbookPath", str(self.desktop_workbook)], timeout=180),
            "threaded-comments": lambda: self.run_foundry(["threaded-comment", "list", "-WorkbookPath", str(self.desktop_workbook)], timeout=180),
            "exports": lambda: self.run_foundry(["workbook", "inspect", "-WorkbookPath", str(self.desktop_workbook)], timeout=180),
            "privacy": lambda: self.run_foundry(["workbook", "document-inspect", "-WorkbookPath", str(self.desktop_workbook)], timeout=180),
            "shapes": lambda: self.run_foundry(["shape", "list", "-WorkbookPath", str(self.desktop_workbook)], timeout=180),
            "pictures": lambda: self.run_foundry(["picture", "list", "-WorkbookPath", str(self.desktop_workbook)], timeout=180),
            "controls": lambda: self.run_foundry(["control", "list", "-WorkbookPath", str(self.desktop_workbook)], timeout=180),
            "pivots": lambda: self.run_foundry(["pivot", "list", "-WorkbookPath", str(self.desktop_workbook)], timeout=180),
            "pivot-charts": lambda: self.run_foundry(["pivot-chart", "list", "-WorkbookPath", str(self.desktop_workbook)], timeout=180),
            "slicers": lambda: self.run_foundry(["slicer", "list", "-WorkbookPath", str(self.desktop_workbook)], timeout=180),
            "timelines": lambda: self.run_foundry(["timeline", "list", "-WorkbookPath", str(self.desktop_workbook)], timeout=180),
            "pq": lambda: self.run_foundry(["query", "list", "-WorkbookPath", str(self.desktop_workbook)], timeout=180),
            "connections": lambda: self.run_foundry(["connection", "list", "-WorkbookPath", str(self.desktop_workbook)], timeout=180),
            "links": lambda: self.run_foundry(["workbook", "links", "-WorkbookPath", str(self.desktop_workbook)], timeout=180),
            "formula-audit": lambda: self.run_foundry(["formula-audit", "inspect", "-WorkbookPath", str(self.desktop_workbook)], timeout=180),
            "cube-functions": lambda: self.run_foundry(["cube-function", "list", "-WorkbookPath", str(self.desktop_workbook)], timeout=180),
            "external-data-ranges": lambda: self.run_foundry(["external-data-range", "list", "-WorkbookPath", str(self.desktop_workbook)], timeout=180),
            "encryption": lambda: self.run_foundry(["workbook", "inspect", "-WorkbookPath", str(self.desktop_workbook)], timeout=180),
            "solver": lambda: self.run_foundry(["solver", "inspect", "-WorkbookPath", str(self.desktop_workbook)], timeout=180),
            "forecast-sheets": lambda: self.run_foundry(["forecast-sheet", "inspect", "-WorkbookPath", str(self.desktop_workbook)], timeout=180),
            "data-tables": lambda: self.run_foundry(["data-table", "list", "-WorkbookPath", str(self.desktop_workbook)], timeout=180),
            "what-if": lambda: self.run_foundry(["what-if", "inspect", "-WorkbookPath", str(self.desktop_workbook)], timeout=180),
            "vba": lambda: self.run_foundry(["automation", "inspect", "-WorkbookPath", str(self.desktop_workbook)], timeout=180),
        }
        return commands.get(surface_id)

    def _desktop_pdf_export(self) -> dict[str, Any]:
        target = self.run_root / "matrix-live-export.pdf"
        return self.run_foundry([
            "workbook", "safe-export", "-WorkbookPath", str(self.desktop_workbook), "-TargetPath", str(target),
            "-SpecJson", '{"breakLinks":false,"removeDocumentInfoTypes":[],"runDocumentInspectors":false}',
        ], timeout=180)

    def _create_sheet_and_readback(self) -> dict[str, Any]:
        self.run_foundry(["sheet", "create", "-WorkbookPath", str(self.workbook), "-Sheet", "CreatedByMatrix"])
        payload = self.run_foundry(["sheet", "list", "-WorkbookPath", str(self.workbook)])
        self.assertIn("CreatedByMatrix", json.dumps(payload))
        return payload

    def _delete_sheet_and_readback(self) -> dict[str, Any]:
        self.run_foundry(["sheet", "delete", "-WorkbookPath", str(self.workbook), "-Sheet", "ToDelete", "-Destructive"])
        payload = self.run_foundry(["sheet", "list", "-WorkbookPath", str(self.workbook)])
        self.assertNotIn("ToDelete", json.dumps(payload))
        return payload

    def _reorder_sheets_and_readback(self) -> dict[str, Any]:
        self.run_foundry([
            "sheet", "reorder", "-WorkbookPath", str(self.workbook),
            "-Sheet", "Inputs", "-Sheet", "Sheet1", "-Sheet", "Scratch", "-Sheet", "CreatedByMatrix",
        ])
        return self.run_foundry(["sheet", "list", "-WorkbookPath", str(self.workbook)])

    def _set_cell_and_readback(self) -> dict[str, Any]:
        self.run_foundry(["cell", "set", "-WorkbookPath", str(self.workbook), "-Sheet", "Inputs", "-Address", "C1", "-ValueJson", "42"])
        payload = self.run_foundry(["cell", "get", "-WorkbookPath", str(self.workbook), "-Sheet", "Inputs", "-Address", "C1"])
        self.assertEqual(payload["cell"]["value"], 42)
        return payload

    def _clear_cell_and_readback(self) -> dict[str, Any]:
        self.run_foundry(["cell", "set", "-WorkbookPath", str(self.workbook), "-Sheet", "Inputs", "-Address", "C2", "-ValueJson", '"clear me"'])
        self.run_foundry(["cell", "set", "-WorkbookPath", str(self.workbook), "-Sheet", "Inputs", "-Address", "C2", "-ValueJson", "null"])
        payload = self.run_foundry(["cell", "get", "-WorkbookPath", str(self.workbook), "-Sheet", "Inputs", "-Address", "C2"])
        self.assertIn(payload["cell"].get("value"), (None, ""))
        return payload

    def _set_range_and_readback(self) -> dict[str, Any]:
        self.run_foundry(["range", "set", "-WorkbookPath", str(self.workbook), "-Sheet", "Inputs", "-RangeRef", "D1:E2", "-ValuesJson", '[["x","y"],["z","w"]]'])
        payload = self.run_foundry(["range", "get", "-WorkbookPath", str(self.workbook), "-Sheet", "Inputs", "-RangeRef", "D1:E2"])
        self.assertIn("x", json.dumps(payload))
        return payload

    def _clear_range_and_readback(self) -> dict[str, Any]:
        self.run_foundry(["range", "set", "-WorkbookPath", str(self.workbook), "-Sheet", "Inputs", "-RangeRef", "F1:F2", "-ValuesJson", '[["clear"],["clear"]]'])
        self.run_foundry(["range", "set", "-WorkbookPath", str(self.workbook), "-Sheet", "Inputs", "-RangeRef", "F1:F2", "-ValuesJson", "[[null],[null]]"])
        payload = self.run_foundry(["range", "get", "-WorkbookPath", str(self.workbook), "-Sheet", "Inputs", "-RangeRef", "F1:F2"])
        self.assertNotIn("clear", json.dumps(payload))
        return payload

    def _create_name_and_readback(self) -> dict[str, Any]:
        self.run_foundry(["name", "set", "-WorkbookPath", str(self.workbook), "-Name", "MatrixCreatedName", "-RefersTo", "=Inputs!$C$1"])
        payload = self.run_foundry(["name", "list", "-WorkbookPath", str(self.workbook)])
        self.assertIn("MatrixCreatedName", json.dumps(payload))
        return payload

    def _update_name_and_readback(self) -> dict[str, Any]:
        self.run_foundry(["name", "set", "-WorkbookPath", str(self.workbook), "-Name", "InitialName", "-RefersTo", "=Inputs!$C$1"])
        payload = self.run_foundry(["name", "list", "-WorkbookPath", str(self.workbook)])
        self.assertIn("$C$1", json.dumps(payload))
        return payload

    def _delete_name_and_readback(self) -> dict[str, Any]:
        self.run_foundry(["name", "set", "-WorkbookPath", str(self.workbook), "-Name", "MatrixDeleteName", "-RefersTo", "=Inputs!$A$1"])
        self.run_foundry(["name", "delete", "-WorkbookPath", str(self.workbook), "-Name", "MatrixDeleteName"])
        payload = self.run_foundry(["name", "list", "-WorkbookPath", str(self.workbook)])
        self.assertNotIn("MatrixDeleteName", json.dumps(payload))
        return payload

    def _inventory_package_surface(self, surface_id: str) -> dict[str, Any]:
        surface = self._package_query_surface(surface_id)
        if surface not in self.surface_sync_cache:
            self.surface_sync_cache.add(surface)
        return self.run_foundry(["query", "-WorkbookPath", str(self.workbook), "-Surface", surface])

    def _can_inventory_package_surface(self, surface: dict[str, Any]) -> bool:
        return surface.get("package") in {"supported", "partial", "preserve-only"} and self._package_query_surface(surface["id"]) is not None

    def _package_query_surface(self, surface_id: str) -> str | None:
        aliases = {
            "workbook": "workbook",
            "sheets": "sheets",
            "rows-columns": "dimensions",
            "tables": "tables",
            "names": "names",
            "formulas": "formulas",
            "data-validation": "data-validation",
            "cf": "cf",
            "styles": "styles",
            "themes": "themes",
            "hyperlinks": "hyperlinks",
            "comments": "comments",
            "print": "print",
            "protection": "protection",
            "charts": "charts",
            "pivots": "pivots",
            "pq": "pq",
            "connections": "connections",
            "model": "model",
            "calc-engine": "workbook,formulas",
            "lambda-names": "names,formulas",
            "workbook-views": "workbook",
            "external-files": "workbook,connections,pq",
            "legacy-bi": "model,pivots,connections",
            "sparklines": "workbook",
            "xml-maps": "workbook",
            "custom-xml": "workbook",
            "ole-objects": "workbook",
            "signatures": "workbook",
            "sensitivity-irm": "workbook",
            "artifact-workbook": "workbook",
        }
        return aliases.get(surface_id)

    def _matrix_limitation(self, surface: dict[str, Any], operation: str) -> dict[str, Any]:
        return {
            "route": surface.get("route"),
            "supportLevel": surface.get("supportLevel"),
            "package": surface.get("package"),
            "desktop": surface.get("desktop"),
            "graph": surface.get("graph"),
            "tomFabric": surface.get("tomFabric"),
            "operation": operation,
            "hostRequirements": surface.get("hostRequirements", []),
            "closureReason": surface.get("closureReason"),
        }

    def _evidence(self, surface: dict[str, Any], operation: str, status: str, *, payload: dict[str, Any], readback: bool, changed: bool) -> dict[str, Any]:
        backend = payload.get("backend") or surface.get("readLane") or surface.get("writeLane") or surface.get("route")
        limitations = [] if status == "executed" else [self._matrix_limitation(surface, operation)]
        return {
            "surface": surface["id"],
            "operation": operation,
            "status": status,
            "backend": backend,
            "changed": changed,
            "readback": readback,
            "warnings": payload.get("warnings", []),
            "limitations": limitations,
            "secretHandling": "runtime-redacted-never-stored",
            "route": surface.get("route"),
            "supportLevel": surface.get("supportLevel"),
            "payloadKeys": sorted(payload.keys()),
        }

    def _assert_standard_evidence(self, surface: dict[str, Any], operation: str, evidence: dict[str, Any]) -> None:
        self.assertEqual(surface["id"], evidence["surface"])
        self.assertEqual(operation, evidence["operation"])
        for field in self.matrix["defaultResponseFields"]:
            self.assertIn(field, evidence)
        self.assertIn(evidence["status"], {"executed", "inventory", "desktop-inventory", "dry-run", "limitation"})
        self.assertIsInstance(evidence["warnings"], list)
        self.assertIsInstance(evidence["limitations"], list)
        self.assertEqual("runtime-redacted-never-stored", evidence["secretHandling"])
        if evidence["status"] == "limitation":
            self.assertTrue(evidence["limitations"])

    def _is_cloud_surface(self, surface: dict[str, Any]) -> bool:
        return surface.get("route") in {"graph-write", "tom-fabric-write"} or surface.get("graph") == "supported" or surface.get("tomFabric") == "supported"

    def _operation_changes(self, operation: str) -> bool:
        return operation in {
            "create", "update", "delete", "clear", "copy", "move", "rename", "protect", "unprotect",
            "set", "execute", "refresh", "recalculate", "export",
        }

    def _real_package_operations(self) -> set[tuple[str, str]]:
        return {
            ("workbook", "create"),
            ("workbook", "get"),
            ("workbook", "inspect"),
            ("sheets", "list"),
            ("sheets", "get"),
            ("sheets", "create"),
            ("sheets", "delete"),
            ("sheets", "move"),
            ("cells", "get"),
            ("cells", "update"),
            ("cells", "clear"),
            ("ranges", "get"),
            ("ranges", "update"),
            ("ranges", "clear"),
            ("names", "list"),
            ("names", "get"),
            ("names", "create"),
            ("names", "update"),
            ("names", "delete"),
            ("formulas", "list"),
            ("formulas", "get"),
            ("data-validation", "list"),
            ("data-validation", "get"),
            ("cf", "list"),
            ("cf", "get"),
            ("hyperlinks", "list"),
            ("hyperlinks", "get"),
            ("comments", "list"),
            ("comments", "get"),
            ("print", "get"),
            ("print", "inspect"),
            ("protection", "get"),
            ("protection", "inspect"),
            ("tables", "list"),
            ("tables", "get"),
            ("charts", "list"),
            ("charts", "get"),
            ("external-files", "list"),
            ("external-files", "inspect"),
        }

    def run_foundry(self, args: list[str], timeout: int = 180) -> dict[str, Any]:
        cache_key = tuple(args)
        mutating = self._is_mutating_command(args)
        if not mutating and cache_key in self.command_cache:
            return json.loads(json.dumps(self.command_cache[cache_key]))
        command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(LAUNCHER), *args]
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        self._assert_no_secret_text(completed.stdout, "stdout")
        self._assert_no_secret_text(completed.stderr, "stderr")
        if completed.returncode != 0:
            self.fail(f"excel-foundry command failed ({completed.returncode}): {' '.join(args)}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}")
        payload = self._parse_json_stdout(completed.stdout, args)
        if mutating:
            self.command_cache.clear()
        else:
            self.command_cache[cache_key] = json.loads(json.dumps(payload))
        return payload

    def _is_mutating_command(self, args: list[str]) -> bool:
        command = args[0] if args else ""
        return command in {
            "workbook", "sheet", "name", "cell", "range", "name-set", "name-delete",
        } and not (len(args) > 1 and args[1] in {"inspect", "capabilities", "list", "get"})

    def _parse_json_stdout(self, stdout: str, args: list[str]) -> dict[str, Any]:
        text = stdout.strip()
        self.assertTrue(text, f"empty stdout for {' '.join(args)}")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            raise

    def _assert_no_secret_leaks(self) -> None:
        for path in self.run_root.rglob("*"):
            if path.is_file():
                self._assert_no_secret_text(path.read_text(encoding="utf-8", errors="ignore"), str(path))

    def _assert_no_secret_text(self, text: str, source: str) -> None:
        for name, secret in self.secrets.items():
            if secret and secret in text:
                self.fail(f"{name} leaked in {source}")


if __name__ == "__main__":
    unittest.main()
