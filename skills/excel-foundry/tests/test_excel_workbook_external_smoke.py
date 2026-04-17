from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PS1 = ROOT / "scripts" / "excel-foundry.ps1"
PYTHON_CLI = ROOT / "scripts" / "excel_workbook_sync.py"
PACKAGE_READABLE_EXTENSIONS = {".xlsx", ".xlsm", ".xltx", ".xltm", ".xlam"}
EXCEL_EXTENSIONS = {".xls", ".xlsx", ".xlsm", ".xlsb", ".xltx", ".xltm", ".xlam"}


def split_external_roots(raw: str) -> list[Path]:
    return [Path(item) for item in raw.split(os.pathsep) if item.strip()]


def discover_external_workbooks(roots: list[Path]) -> list[Path]:
    discovered: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        if root.is_file():
            if root.suffix.lower() not in EXCEL_EXTENSIONS:
                continue
            resolved = root.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            discovered.append(resolved)
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in EXCEL_EXTENSIONS:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            discovered.append(resolved)
    return sorted(discovered)


def safe_slug(path: Path) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(path))
    return normalized.strip(".-") or path.stem


class ExcelWorkbookExternalSmokeHelperTests(unittest.TestCase):
    def test_discover_external_workbooks_accepts_explicit_file_roots(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-sync-external-root-file-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "single.xlsx"
            workbook.write_text("placeholder", encoding="utf-8")

            discovered = discover_external_workbooks([workbook])

            self.assertEqual(discovered, [workbook.resolve()])


class ExcelWorkbookExternalSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw_roots = os.environ.get("EXCEL_SYNC_EXTERNAL_ROOTS", "")
        if not raw_roots.strip():
            raise unittest.SkipTest("set EXCEL_SYNC_EXTERNAL_ROOTS to run external corpus smoke tests")
        cls.roots = split_external_roots(raw_roots)
        cls.workbooks = discover_external_workbooks(cls.roots)
        if not cls.workbooks:
            raise unittest.SkipTest("no Excel workbooks were discovered under EXCEL_SYNC_EXTERNAL_ROOTS")
        cls.package_workbooks = [path for path in cls.workbooks if path.suffix.lower() in PACKAGE_READABLE_EXTENSIONS]
        cls.audit_limit = max(0, int(os.environ.get("EXCEL_SYNC_EXTERNAL_AUDIT_LIMIT", "3")))

    def test_generic_pull_and_compare_are_invariant_safe(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-sync-external-generic-") as tmpdir:
            tmp = Path(tmpdir)
            for workbook in self.workbooks:
                slug = safe_slug(workbook)
                with self.subTest(workbook=str(workbook)):
                    pull_root = tmp / "pull" / slug
                    pull_proc = subprocess.run(
                        [
                            "python",
                            str(PYTHON_CLI),
                            "pull",
                            "--workbook",
                            str(workbook),
                            "--output-root",
                            str(pull_root),
                            "--engine",
                            "auto",
                        ],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        check=False,
                        timeout=300,
                    )
                    self.assertEqual(pull_proc.returncode, 0, pull_proc.stdout + pull_proc.stderr)
                    pull_payload = json.loads(pull_proc.stdout)
                    self.assertTrue((pull_root / "normalized.json").exists())
                    self.assertIn("engine", pull_payload)

                    compare_root = tmp / "compare" / slug
                    compare_proc = subprocess.run(
                        [
                            "python",
                            str(PYTHON_CLI),
                            "compare",
                            "--workbook",
                            str(workbook),
                            "--output-root",
                            str(compare_root),
                            "--engine",
                            "auto",
                        ],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        check=False,
                        timeout=300,
                    )
                    self.assertEqual(compare_proc.returncode, 0, compare_proc.stdout + compare_proc.stderr)
                    compare_payload = json.loads(compare_proc.stdout)
                    self.assertIn("comparisonAvailable", compare_payload)
                    self.assertIn("comparisonStatus", compare_payload)
                    if compare_payload["comparisonAvailable"]:
                        self.assertIn(compare_payload["comparisonStatus"], {"ok"})
                        self.assertIn(compare_payload["match"], {True, False})
                        raw_payload = compare_payload.get("raw")
                        normalized_payload = compare_payload.get("normalized")
                        if raw_payload is not None:
                            self.assertIn(raw_payload["match"], {True, False})
                        if normalized_payload is not None:
                            self.assertIn(normalized_payload["match"], {True, False})
                    else:
                        self.assertIsNone(compare_payload["match"])
                        raw_payload = compare_payload.get("raw")
                        normalized_payload = compare_payload.get("normalized")
                        if raw_payload is not None:
                            self.assertIsNone(raw_payload["match"])
                        if normalized_payload is not None:
                            self.assertIsNone(normalized_payload["match"])
                        self.assertIn(compare_payload["comparisonStatus"], {"com_open_failed", "com_timed_out", "com_unavailable", "package_unavailable"})

    @unittest.skipUnless(shutil.which("pwsh") is not None, "pwsh not available on this host")
    def test_package_manifest_flows_report_capabilities_and_unsupported(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-sync-external-package-") as tmpdir:
            tmp = Path(tmpdir)
            for workbook in self.package_workbooks:
                slug = safe_slug(workbook)
                with self.subTest(workbook=str(workbook)):
                    inspect_proc = subprocess.run(
                        [
                            "pwsh",
                            "-NoProfile",
                            "-File",
                            str(PS1),
                            "inspect",
                            "--workbook-path",
                            str(workbook),
                            "--backend",
                            "package",
                        ],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        check=False,
                        timeout=180,
                    )
                    self.assertEqual(inspect_proc.returncode, 0, inspect_proc.stdout + inspect_proc.stderr)
                    inspect_payload = json.loads(inspect_proc.stdout)
                    self.assertEqual(inspect_payload["backend"], "package")
                    self.assertIn("capabilities", inspect_payload)
                    self.assertIn("warnings", inspect_payload)
                    self.assertIn("unsupported", inspect_payload)
                    self.assertTrue(inspect_payload["capabilities"]["canWrite"])

                    query_proc = subprocess.run(
                        [
                            "pwsh",
                            "-NoProfile",
                            "-File",
                            str(PS1),
                            "query",
                            "--workbook-path",
                            str(workbook),
                            "--surface",
                            "tables,names,conditional-formatting,formulas,data-validation,protection,charts,pivots,pq,connections,model,project",
                            "--backend",
                            "package",
                        ],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        check=False,
                        timeout=240,
                    )
                    self.assertEqual(query_proc.returncode, 0, query_proc.stdout + query_proc.stderr)
                    query_payload = json.loads(query_proc.stdout)
                    self.assertEqual(query_payload["backend"], "package")
                    self.assertIn("capabilities", query_payload)
                    self.assertIn("warnings", query_payload)
                    self.assertIn("unsupported", query_payload)

                    output_dir = tmp / "bootstrap" / slug
                    bootstrap_proc = subprocess.run(
                        [
                            "pwsh",
                            "-NoProfile",
                            "-File",
                            str(PS1),
                            "bootstrap",
                            "--workbook-path",
                            str(workbook),
                            "--output-dir",
                            str(output_dir),
                            "--backend",
                            "package",
                        ],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        check=False,
                        timeout=240,
                    )
                    self.assertEqual(bootstrap_proc.returncode, 0, bootstrap_proc.stdout + bootstrap_proc.stderr)
                    self.assertTrue((output_dir / "excel-sync.manifest.json").exists())

    def test_audit_and_matrix_continue_when_compare_is_unavailable(self) -> None:
        if self.audit_limit == 0:
            self.skipTest("set EXCEL_SYNC_EXTERNAL_AUDIT_LIMIT to a positive value to run audit smoke")
        sample = self.workbooks[: self.audit_limit]
        with tempfile.TemporaryDirectory(prefix="excel-sync-external-audit-") as tmpdir:
            tmp = Path(tmpdir)
            for workbook in sample:
                slug = safe_slug(workbook)
                with self.subTest(workbook=str(workbook)):
                    audit_root = tmp / "audit" / slug
                    audit_proc = subprocess.run(
                        [
                            "python",
                            str(PYTHON_CLI),
                            "audit",
                            "--workbook",
                            str(workbook),
                            "--output-root",
                            str(audit_root),
                            "--engine",
                            "auto",
                        ],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        check=False,
                        timeout=600,
                    )
                    self.assertEqual(audit_proc.returncode, 0, audit_proc.stdout + audit_proc.stderr)
                    audit_payload = json.loads(audit_proc.stdout)
                    run_root = Path(audit_payload["reportsRoot"]).parent
                    self.assertTrue((run_root / "original-copy").exists())
                    self.assertTrue((run_root / "baseline").exists())
                    self.assertTrue((run_root / "post-mutation").exists() or audit_payload["mutationReport"].get("timedOut"))
                    self.assertIn("comparisonStatus", audit_payload["baselineCompare"])
                    self.assertIn("comparisonStatus", audit_payload["postMutationCompare"])

            matrix_root = tmp / "matrix"
            command = [
                "python",
                str(PYTHON_CLI),
                "matrix-audit",
                "--output-root",
                str(matrix_root),
                "--engine",
                "auto",
            ]
            for workbook in sample:
                command.extend(["--workbook", str(workbook)])
            matrix_proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=900,
            )
            self.assertEqual(matrix_proc.returncode, 0, matrix_proc.stdout + matrix_proc.stderr)
            matrix_payload = json.loads(matrix_proc.stdout)
            self.assertEqual(len(matrix_payload["workbooks"]), len(sample))
            for workbook_payload in matrix_payload["workbooks"]:
                self.assertIn("baselineComparisonStatus", workbook_payload)
                self.assertIn("postMutationComparisonStatus", workbook_payload)
                self.assertIn("baselineComparisonAvailable", workbook_payload)
                self.assertIn("postMutationComparisonAvailable", workbook_payload)


if __name__ == "__main__":
    unittest.main()
