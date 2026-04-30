from __future__ import annotations

import json
import importlib.util
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PS1 = ROOT / "scripts" / "excel-foundry.ps1"
PYTHON_CLI = ROOT / "scripts" / "excel_workbook_sync.py"
PACKAGE_CLI = ROOT / "scripts" / "excel_workbook_package.py"
PACKAGE_READABLE_EXTENSIONS = {".xlsx", ".xlsm", ".xltx", ".xltm", ".xlam"}
EXCEL_EXTENSIONS = {".xls", ".xlsx", ".xlsm", ".xlsb", ".xltx", ".xltm", ".xlam"}
FLAT_EXPORT_EXTENSIONS = {".csv", ".txt", ".ods"}
DISCOVERABLE_EXTENSIONS = EXCEL_EXTENSIONS | FLAT_EXPORT_EXTENSIONS


def split_external_roots(raw: str) -> list[Path]:
    return [Path(item) for item in raw.split(os.pathsep) if item.strip()]


def copy_external_roots_to_temp(roots: list[Path], destination: Path) -> list[Path]:
    copied_roots: list[Path] = []
    destination.mkdir(parents=True, exist_ok=True)
    for index, root in enumerate(roots, start=1):
        if not root.exists():
            continue
        root_hash = sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:10]
        if root.is_file():
            target = destination / f"{index:02d}-{root_hash}{root.suffix.lower()}"
            shutil.copy2(root, target)
            copied_roots.append(target)
            continue
        target = destination / f"{index:02d}-{root_hash}"
        shutil.copytree(root, target)
        copied_roots.append(target)
    return copied_roots


def load_package_module():
    spec = importlib.util.spec_from_file_location("excel_workbook_package_external_smoke", PACKAGE_CLI)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def create_generated_external_corpus(destination: Path) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    package_module = load_package_module()
    workbook = destination / "generated-corpus.xlsx"
    package_module.create_blank_workbook(
        workbook,
        {
            "title": "Generated External Smoke Corpus",
            "subject": "Excel Foundry test corpus",
            "description": "Disposable package-readable workbook generated at test runtime.",
            "sheets": ["DATA_RECORDS", "DATA_RECORD_LINES"],
            "customProperties": {"Corpus": "generated"},
        },
    )
    (destination / "flat-export.csv").write_text("Record,Amount\nINV-001,10\n", encoding="utf-8")
    (destination / "flat-export.txt").write_text("Record\tAmount\nINV-002\t20\n", encoding="utf-8")
    (destination / "flat-export.ods").write_text("placeholder\n", encoding="utf-8")
    return [destination]


def discover_external_files(roots: list[Path], extensions: set[str] = DISCOVERABLE_EXTENSIONS) -> list[Path]:
    discovered: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        if root.is_file():
            if root.suffix.lower() not in extensions:
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
            if path.suffix.lower() not in extensions:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            discovered.append(resolved)
    return sorted(discovered)


def discover_external_workbooks(roots: list[Path]) -> list[Path]:
    return discover_external_files(roots, EXCEL_EXTENSIONS)


def safe_slug(path: Path, ordinal: int = 1) -> str:
    normalized_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", path.stem).strip(".-") or "workbook"
    normalized_stem = normalized_stem[:48].strip(".-") or "workbook"
    digest = sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:12]
    return f"{ordinal:03d}-{normalized_stem}-{digest}"


class ExcelWorkbookExternalSmokeHelperTests(unittest.TestCase):
    def test_discover_external_workbooks_accepts_explicit_file_roots(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-sync-external-root-file-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "single.xlsx"
            workbook.write_text("placeholder", encoding="utf-8")

            discovered = discover_external_workbooks([workbook])

            self.assertEqual(discovered, [workbook.resolve()])

    def test_discover_external_files_classifies_flat_exports_without_workbook_smoke(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-sync-external-flat-") as tmpdir:
            tmp = Path(tmpdir)
            csv_file = tmp / "export.csv"
            txt_file = tmp / "export.txt"
            ods_file = tmp / "export.ods"
            csv_file.write_text("a,b\n1,2\n", encoding="utf-8")
            txt_file.write_text("a\tb\n1\t2\n", encoding="utf-8")
            ods_file.write_text("placeholder", encoding="utf-8")

            discovered = discover_external_files([tmp])
            workbooks = discover_external_workbooks([tmp])

            self.assertEqual({path.suffix for path in discovered}, {".csv", ".txt", ".ods"})
            self.assertEqual(workbooks, [])

    def test_safe_slug_is_bounded_and_stable_for_deep_windows_paths(self) -> None:
        path = Path("C:/very/deep/" + "/".join(["nested-directory"] * 20)) / "Macro Workbook With Spaces.xlsm"

        first = safe_slug(path, 7)
        second = safe_slug(path, 7)

        self.assertEqual(first, second)
        self.assertLessEqual(len(first), 68)
        self.assertTrue(first.startswith("007-Macro-Workbook-With-Spaces-"))


class ExcelWorkbookExternalSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw_roots = os.environ.get("EXCEL_SYNC_EXTERNAL_ROOTS", "")
        cls.corpus_copy = tempfile.TemporaryDirectory(prefix="excel-sync-external-corpus-")
        corpus_root = Path(cls.corpus_copy.name)
        if raw_roots.strip():
            cls.original_roots = split_external_roots(raw_roots)
            cls.roots = copy_external_roots_to_temp(cls.original_roots, corpus_root)
            cls.generated_corpus = False
        else:
            cls.original_roots = []
            cls.roots = create_generated_external_corpus(corpus_root)
            cls.generated_corpus = True
        cls.files = discover_external_files(cls.roots)
        cls.workbooks = [path for path in cls.files if path.suffix.lower() in EXCEL_EXTENSIONS]
        cls.flat_exports = [path for path in cls.files if path.suffix.lower() in FLAT_EXPORT_EXTENSIONS]
        if not cls.workbooks:
            if raw_roots.strip():
                raise AssertionError("EXCEL_SYNC_EXTERNAL_ROOTS was provided, but no Excel workbooks were discovered under the copied roots")
            raise AssertionError("generated external smoke corpus did not contain an Excel workbook")
        cls.package_workbooks = [path for path in cls.workbooks if path.suffix.lower() in PACKAGE_READABLE_EXTENSIONS]
        cls.generic_limit = max(0, int(os.environ.get("EXCEL_SYNC_EXTERNAL_GENERIC_LIMIT", "3")))
        cls.package_limit = max(0, int(os.environ.get("EXCEL_SYNC_EXTERNAL_PACKAGE_LIMIT", "3")))
        cls.audit_limit = max(0, int(os.environ.get("EXCEL_SYNC_EXTERNAL_AUDIT_LIMIT", "3")))

    @classmethod
    def tearDownClass(cls) -> None:
        corpus_copy = getattr(cls, "corpus_copy", None)
        if corpus_copy is not None:
            corpus_copy.cleanup()

    def test_generic_pull_and_compare_are_invariant_safe(self) -> None:
        if self.generic_limit == 0:
            self.skipTest("set EXCEL_SYNC_EXTERNAL_GENERIC_LIMIT to a positive value to run generic corpus smoke")
        sample = self.workbooks[: self.generic_limit]
        with tempfile.TemporaryDirectory(prefix="excel-sync-external-generic-") as tmpdir:
            tmp = Path(tmpdir)
            for index, workbook in enumerate(sample, start=1):
                slug = safe_slug(workbook, index)
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
                            "--stdout",
                            "full",
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
                            "--stdout",
                            "full",
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
        if self.package_limit == 0:
            self.skipTest("set EXCEL_SYNC_EXTERNAL_PACKAGE_LIMIT to a positive value to run package corpus smoke")
        sample = self.package_workbooks[: self.package_limit]
        if not sample:
            self.fail("no package-readable Excel workbooks were discovered in the external smoke corpus")
        with tempfile.TemporaryDirectory(prefix="excel-sync-external-package-") as tmpdir:
            tmp = Path(tmpdir)
            for index, workbook in enumerate(sample, start=1):
                slug = safe_slug(workbook, index)
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
            for index, workbook in enumerate(sample, start=1):
                slug = safe_slug(workbook, index)
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
                            "--stdout",
                            "full",
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
                "--stdout",
                "full",
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
