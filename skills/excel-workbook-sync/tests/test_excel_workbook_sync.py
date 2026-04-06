from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
import base64
from io import BytesIO
from pathlib import Path
from textwrap import dedent


ROOT = Path(__file__).resolve().parents[1]
POSIX = ROOT / "scripts" / "excel-workbook-sync"
CMD = ROOT / "scripts" / "excel-workbook-sync.cmd"
PS1 = ROOT / "scripts" / "excel-workbook-sync.ps1"
COMMON = ROOT / "scripts" / "ExcelSync.Common.ps1"
POWERQUERY = ROOT / "scripts" / "sync-excel-powerquery.ps1"
OPENAI_YAML = ROOT / "agents" / "openai.yaml"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "tr_upload_sheet"
FIXTURE_MANIFEST = ROOT / "tests" / "fixtures" / "tr_upload_sheet" / "excel-sync.manifest.json"
FIXTURE_WORKBOOK = FIXTURE_DIR / "tr_upload_template.xlsm"
HAS_PWSH = shutil.which("pwsh") is not None
HAS_CMD = shutil.which("cmd") is not None


def run_pwsh(command: str, *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    if not HAS_PWSH:
        raise unittest.SkipTest("pwsh not available on this host")
    return subprocess.run(
        ["pwsh", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def run_pwsh_file(*args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    if not HAS_PWSH:
        raise unittest.SkipTest("pwsh not available on this host")
    return subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(PS1), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def build_minimal_ooxml_workbook(workbook_path: Path) -> None:
    mashup_buffer = BytesIO()
    with zipfile.ZipFile(mashup_buffer, "w", compression=zipfile.ZIP_DEFLATED) as mashup_zip:
        mashup_zip.writestr("[Content_Types].xml", "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'/>")
        mashup_zip.writestr("Config/Package.xml", "<Package />")
        mashup_zip.writestr(
            "Formulas/Section1.m",
            dedent(
                """\
                section Section1;
                shared Query1 =
                let
                    Source = #table({"Name","Value"}, {{"Alpha", 1}})
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
              <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
              <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
              <Override PartName="/xl/tables/table1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.table+xml"/>
              <Override PartName="/xl/queryTables/queryTable1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.queryTable+xml"/>
              <Override PartName="/xl/connections.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.connections+xml"/>
              <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
              <Override PartName="/customXml/item1.xml" ContentType="application/xml"/>
              <Override PartName="/customXml/itemProps1.xml" ContentType="application/vnd.openxmlformats-officedocument.customXmlProperties+xml"/>
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
                <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
              </sheets>
              <definedNames>
                <definedName name="MyValue">Sheet1!$B$2</definedName>
              </definedNames>
            </workbook>
            """
        ),
        "xl/_rels/workbook.xml.rels": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
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
                  <c r="B2"><v>1</v></c>
                </row>
              </sheetData>
              <conditionalFormatting sqref="B2">
                <cfRule type="expression" priority="1">
                  <formula>B2&gt;0</formula>
                </cfRule>
              </conditionalFormatting>
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
        "xl/tables/table1.xml": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <table xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" id="1" name="Table1" displayName="Table1" ref="A1:B2" totalsRowShown="0">
              <autoFilter ref="A1:B2"/>
              <tableColumns count="2">
                <tableColumn id="1" name="Name"/>
                <tableColumn id="2" name="Value"/>
              </tableColumns>
              <tableStyleInfo name="TableStyleMedium2" showFirstColumn="0" showLastColumn="0" showRowStripes="1" showColumnStripes="0"/>
            </table>
            """
        ),
        "xl/tables/_rels/table1.xml.rels": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/queryTable" Target="../queryTables/queryTable1.xml"/>
            </Relationships>
            """
        ),
        "xl/queryTables/queryTable1.xml": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <queryTable xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" connectionId="1"/>
            """
        ),
        "xl/connections.xml": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <connections xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <connection id="1" name="Query - Query1" description="Connection to Query1" type="1" background="1">
                <dbPr connection="Provider=Microsoft.Mashup.OleDb.1;Data Source=$Workbook$;Location=Query1;Extended Properties=&quot;&quot;;" command="SELECT * FROM [Query1]"/>
              </connection>
            </connections>
            """
        ),
        "xl/sharedStrings.xml": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="3" uniqueCount="3">
              <si><t>Name</t></si>
              <si><t>Value</t></si>
              <si><t>Alpha</t></si>
            </sst>
            """
        ),
        "customXml/item1.xml": f'<?xml version="1.0" encoding="utf-8"?><DataMashup xmlns="http://schemas.microsoft.com/DataMashup">{mashup_base64}</DataMashup>',
        "customXml/itemProps1.xml": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <ds:datastoreItem ds:itemID="{12345678-1234-1234-1234-1234567890AB}" xmlns:ds="http://schemas.openxmlformats.org/officeDocument/2006/customXml">
              <ds:schemaRefs>
                <ds:schemaRef ds:uri="http://schemas.microsoft.com/DataMashup"/>
              </ds:schemaRefs>
            </ds:datastoreItem>
            """
        ),
    }

    with zipfile.ZipFile(workbook_path, "w", compression=zipfile.ZIP_DEFLATED) as workbook_zip:
        for name, content in workbook_files.items():
            workbook_zip.writestr(name, content)


class ExcelWorkbookSyncSkillTests(unittest.TestCase):
    def test_expected_files_exist(self) -> None:
        self.assertTrue((ROOT / "SKILL.md").exists())
        self.assertTrue(OPENAI_YAML.exists())
        self.assertTrue(POSIX.exists())
        self.assertTrue(CMD.exists())
        self.assertTrue(PS1.exists())
        self.assertTrue(FIXTURE_MANIFEST.exists())
        self.assertTrue(COMMON.exists())
        self.assertTrue(POWERQUERY.exists())

    def test_openai_yaml_interface_only(self) -> None:
        content = OPENAI_YAML.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("interface:\n"))
        self.assertNotIn("metadata:", content)

    def test_fixture_manifest_exercises_richer_surfaces(self) -> None:
        manifest = json.loads(FIXTURE_MANIFEST.read_text(encoding="utf-8"))
        self.assertIn("vbaProject", manifest)
        self.assertIn("powerQuery", manifest)
        self.assertEqual(manifest["structure"]["conditionalFormattingDiscovery"]["mode"], "all-major")
        self.assertIn("projectPath", manifest["vbaProject"])
        self.assertIn("referencesPath", manifest["vbaProject"])
        self.assertIn("queriesDirectory", manifest["powerQuery"])
        self.assertIn("queriesPath", manifest["powerQuery"])

    def test_manifest_resolution_resolves_relative_paths(self) -> None:
        proc = run_pwsh(
            (
                f". '{COMMON}'; "
                f"$resolved = Resolve-ExcelSyncManifest -ManifestPath '{FIXTURE_MANIFEST}'; "
                "[pscustomobject]@{"
                "manifestPath=$resolved.ManifestPath;"
                "workbookPath=$resolved.WorkbookPath;"
                "vbaCount=@($resolved.VbaComponents).Count;"
                "projectPath=$resolved.VbaProject.ProjectPath;"
                "referencesPath=$resolved.VbaProject.ReferencesPath;"
                "tablesPath=$resolved.Structure.TablesPath;"
                "pqDir=$resolved.PowerQuery.QueriesDirectory;"
                "pqQueriesPath=$resolved.PowerQuery.QueriesPath;"
                "} | ConvertTo-Json -Compress -Depth 20"
            )
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(Path(payload["manifestPath"]), FIXTURE_MANIFEST.resolve())
        self.assertEqual(Path(payload["workbookPath"]), FIXTURE_WORKBOOK.resolve())
        self.assertEqual(payload["vbaCount"], 3)
        self.assertEqual(
            Path(payload["projectPath"]),
            (FIXTURE_DIR / "workbook_structure" / "vba_project.json").resolve(),
        )
        self.assertEqual(
            Path(payload["referencesPath"]),
            (FIXTURE_DIR / "workbook_structure" / "vba_references.json").resolve(),
        )
        self.assertEqual(
            Path(payload["tablesPath"]),
            (FIXTURE_DIR / "workbook_structure" / "defaults_tables.json").resolve(),
        )
        self.assertEqual(
            Path(payload["pqDir"]),
            (FIXTURE_DIR / "power_query" / "queries").resolve(),
        )
        self.assertEqual(
            Path(payload["pqQueriesPath"]),
            (FIXTURE_DIR / "power_query" / "queries.json").resolve(),
        )

    def test_manifestless_resolution_for_inspect_query(self) -> None:
        workbook_path = Path(tempfile.gettempdir()) / "excel-workbook-sync-manifestless.xlsm"
        proc = run_pwsh(
            (
                f". '{COMMON}'; "
                f"$resolved = Resolve-ExcelSyncManifest -WorkbookPathOverride '{workbook_path}' -AllowMissingManifestForInspectQuery; "
                "[pscustomobject]@{"
                "manifestPath=$resolved.ManifestPath;"
                "workbookPath=$resolved.WorkbookPath;"
                "vbaCount=@($resolved.VbaComponents).Count;"
                "tablesPath=$resolved.Structure.TablesPath;"
                "pqDir=$resolved.PowerQuery.QueriesDirectory"
                "} | ConvertTo-Json -Compress -Depth 20"
            )
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertIsNone(payload["manifestPath"])
        self.assertEqual(Path(payload["workbookPath"]), workbook_path.resolve())
        self.assertEqual(payload["vbaCount"], 0)
        self.assertIsNone(payload["tablesPath"])
        self.assertIsNone(payload["pqDir"])

    def test_manifest_resolution_accepts_legacy_manifest_without_vba_project(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-workbook-sync-legacy-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "legacy.xlsm"
            workbook.write_bytes(b"")
            manifest = tmp / "excel-sync.manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "workbookPath": "legacy.xlsm",
                        "vbaComponents": [
                            {"name": "Module1", "path": "macros/module1.bas"},
                        ],
                        "structure": {
                            "tablesPath": "structure/tables.json",
                            "namesPath": "structure/names.json",
                            "conditionalFormattingPath": "structure/cf.json",
                            "conditionalFormattingDiscovery": {"mode": "all-formula"},
                        },
                        "powerQuery": {
                            "queriesDirectory": "power_query/queries",
                            "queriesPath": "power_query/queries.json",
                        },
                    }
                ),
                encoding="utf-8",
            )
            proc = run_pwsh(
                (
                    f". '{COMMON}'; "
                    f"$resolved = Resolve-ExcelSyncManifest -ManifestPath '{manifest}'; "
                    "[pscustomobject]@{"
                    "workbookPath=$resolved.WorkbookPath;"
                    "projectPath=$resolved.VbaProject.ProjectPath;"
                    "referencesPath=$resolved.VbaProject.ReferencesPath;"
                    "vbaCount=@($resolved.VbaComponents).Count;"
                    "pqDir=$resolved.PowerQuery.QueriesDirectory"
                    "} | ConvertTo-Json -Compress -Depth 20"
                )
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(Path(payload["workbookPath"]), workbook.resolve())
            self.assertIsNone(payload["projectPath"])
            self.assertIsNone(payload["referencesPath"])
            self.assertEqual(payload["vbaCount"], 1)
            self.assertEqual(Path(payload["pqDir"]), (tmp / "power_query" / "queries").resolve())

    def test_close_excel_workbook_retries_transient_busy_calls(self) -> None:
        proc = run_pwsh(
            dedent(
                f"""
                . '{COMMON}'
                $closeAttempts = 0
                $quitAttempts = 0
                $busy = [System.Runtime.InteropServices.COMException]::new('busy', -2147418111)

                $workbook = [pscustomobject]@{{}}
                $excel = [pscustomobject]@{{}}

                $workbook | Add-Member -MemberType ScriptMethod -Name Close -Value {{
                    param($saveChanges)
                    $script:closeAttempts++
                    if ($script:closeAttempts -lt 2) {{
                        throw $script:busy
                    }}
                }}

                $excel | Add-Member -MemberType ScriptMethod -Name Quit -Value {{
                    $script:quitAttempts++
                    if ($script:quitAttempts -lt 2) {{
                        throw $script:busy
                    }}
                }}

                $context = [pscustomobject]@{{
                    Workbook = $workbook
                    Excel = $excel
                    State = [pscustomobject]@{{
                        AutomationSecurity = $null
                        AskToUpdateLinks = $null
                        EnableEvents = $null
                        ScreenUpdating = $null
                        DisplayAlerts = $null
                        Visible = $null
                    }}
                }}

                Close-ExcelWorkbook -Context $context -SaveChanges:$true
                [pscustomobject]@{{
                    closeAttempts = $closeAttempts
                    quitAttempts = $quitAttempts
                }} | ConvertTo-Json -Compress
                """
            )
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["closeAttempts"], 2)
        self.assertEqual(payload["quitAttempts"], 2)

    def test_inspection_handles_partial_query_payloads(self) -> None:
        proc = run_pwsh(
            dedent(
                f"""
                . '{COMMON}'
                function Get-ExcelWorkbookQuery {{
                    param([string]$WorkbookPath, [string[]]$Surface, [switch]$Visible)
                    return [pscustomobject]@{{
                        workbookPath = $WorkbookPath
                        tables = @(
                            [pscustomobject]@{{ name = 't1' }},
                            [pscustomobject]@{{ name = 't2' }}
                        )
                        names = @(
                            [pscustomobject]@{{ name = 'n1' }}
                        )
                        pq = @(
                            [pscustomobject]@{{ name = 'Matched' }}
                        )
                        connections = @(
                            [pscustomobject]@{{ name = 'Query - Matched' }}
                        )
                        model = [pscustomobject]@{{
                            modelTables = @(
                                [pscustomobject]@{{ name = 'MatchedModel' }}
                            )
                        }}
                        project = [pscustomobject]@{{
                            accessible = $true
                            error = $null
                            componentCount = 3
                            referenceCount = 2
                        }}
                    }}
                }}
                Get-ExcelWorkbookInspection -WorkbookPath 'dummy.xlsm' -Surface @('tables','names','project','pq','connections','model') |
                    ConvertTo-Json -Compress -Depth 20
                """
            )
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["counts"]["tables"], 2)
        self.assertEqual(payload["counts"]["names"], 1)
        self.assertEqual(payload["counts"]["cf"], 0)
        self.assertEqual(payload["counts"]["pq"], 1)
        self.assertEqual(payload["counts"]["connections"], 1)
        self.assertEqual(payload["counts"]["modelTables"], 1)
        self.assertEqual(payload["counts"]["vba"], 0)
        self.assertEqual(payload["counts"]["references"], 0)
        self.assertEqual(payload["project"]["componentCount"], 3)
        self.assertEqual(payload["supportedCfTypes"], [])
        self.assertEqual(payload["unsupportedCfTypes"], [])

    def test_structure_script_has_optional_cf_property_guard(self) -> None:
        content = (ROOT / "scripts" / "sync-excel-structure.ps1").read_text(encoding="utf-8")
        self.assertIn('PSObject.Properties["replaceIfFormulaContains"]', content)

    def test_structure_script_uses_bulk_table_writes(self) -> None:
        content = (ROOT / "scripts" / "sync-excel-structure.ps1").read_text(encoding="utf-8")
        self.assertIn("$target.Value2 = $matrix", content)

    def test_common_script_smoke_copies_workspace_recursively(self) -> None:
        content = COMMON.read_text(encoding="utf-8")
        self.assertIn("Copy-Item -LiteralPath $manifestDirectory -Destination $tempWorkspace -Recurse -Force", content)
        self.assertIn('Remove-Item -LiteralPath $tempRoot -Recurse -Force', content)

    def test_common_script_uses_retry_aware_excel_open_and_quit_cleanup(self) -> None:
        content = COMMON.read_text(encoding="utf-8")
        self.assertIn('Invoke-ExcelComWithRetry -Description "Opening workbook"', content)
        self.assertIn('Invoke-ExcelQuitSafely -Excel $excel -Description "Quitting Excel after failed open" -SwallowErrors', content)
        self.assertIn('Invoke-ExcelQuitSafely -Excel $excel -Description "Quitting Excel"', content)

    def test_common_script_exposes_package_bootstrap_and_surface_aliases(self) -> None:
        content = COMMON.read_text(encoding="utf-8")
        self.assertIn("function Get-NormalizedSurfaceNames", content)
        self.assertIn("function Invoke-ExcelWorkbookBootstrap", content)
        self.assertIn("function Invoke-PackageWorkbookHelper", content)

    def test_posix_launcher_negative_path_is_concise(self) -> None:
        proc = subprocess.run(
            ["sh", str(POSIX), "inspect", "--workbook-path", "/tmp/does-not-matter.xlsm"],
            capture_output=True,
            text=True,
            check=False,
        )
        combined = (proc.stdout + proc.stderr).lower()
        self.assertNotEqual(proc.returncode, 0)
        self.assertTrue(
            ("excel com automation is unavailable" in combined)
            or ("workbook not found" in combined),
            combined,
        )

    def test_posix_launcher_help_is_native(self) -> None:
        proc = subprocess.run(
            ["sh", str(POSIX), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Usage:", proc.stdout)
        self.assertIn("inspect|query|push|pull|roundtrip|smoke|refresh|bootstrap", proc.stdout)

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_powershell_cli_help_is_available(self) -> None:
        proc = run_pwsh_file("--help")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("Usage:", proc.stdout)
        self.assertIn("bootstrap", proc.stdout)
        self.assertIn("GNU-style and native PowerShell flags are both accepted.", proc.stdout)

    def test_posix_launcher_translates_gnu_flags_for_powershell_backend(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-workbook-sync-posix-") as tmpdir:
            tmp = Path(tmpdir)
            record_path = tmp / "args.txt"
            fake_pwsh = tmp / "pwsh"
            fake_pwsh.write_text(
                dedent(
                    f"""\
                    #!/usr/bin/env sh
                    printf '%s\n' "$@" > "{record_path.as_posix()}"
                    """
                ),
                encoding="utf-8",
            )
            fake_pwsh.chmod(0o755)

            env = os.environ.copy()
            env["EXCEL_WORKBOOK_SYNC_POWERSHELL"] = str(fake_pwsh)

            proc = subprocess.run(
                [
                    "sh",
                    str(POSIX),
                    "inspect",
                    "--manifest-path",
                    "/tmp/test manifest.json",
                    "--workbook-path",
                    "/tmp/test workbook.xlsm",
                    "--surface",
                    "tables,names",
                    "--query-name",
                    "Matched",
                    "--visible",
                ],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            args = record_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(args[0:4], ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File"])
            self.assertTrue(args[4].endswith("/scripts/excel-workbook-sync.ps1") or args[4].endswith("\\scripts\\excel-workbook-sync.ps1"))
            self.assertEqual(args[5], "inspect")
            self.assertEqual(args[6], "-ManifestPath")
            self.assertTrue(args[7].lower().endswith("test manifest.json"))
            self.assertEqual(args[8], "-WorkbookPath")
            self.assertTrue(args[9].lower().endswith("test workbook.xlsm"))
            self.assertEqual(args[10:], ["-Surface", "tables,names", "-QueryName", "Matched", "-Visible"])

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_package_backend_query_reads_minimal_ooxml_workbook(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-workbook-sync-package-") as tmpdir:
            workbook = Path(tmpdir) / "package-workbook.xlsx"
            build_minimal_ooxml_workbook(workbook)
            proc = run_pwsh_file(
                "query",
                "--workbook-path",
                str(workbook),
                "--surface",
                "tables,names,conditional-formatting,pq,connections,model",
                "--backend",
                "package",
                timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["backend"], "package")
            self.assertEqual(len(payload["tables"]), 1)
            self.assertEqual(payload["tables"][0]["name"], "Table1")
            self.assertEqual(len(payload["names"]), 1)
            self.assertEqual(payload["names"][0]["name"], "MyValue")
            self.assertEqual(len(payload["cf"]), 1)
            self.assertEqual(len(payload["pq"]), 1)
            self.assertEqual(payload["pq"][0]["name"], "Query1")
            self.assertEqual(payload["pq"][0]["connectionName"], "Query - Query1")
            self.assertEqual(payload["pq"][0]["loads"][0]["table"], "Table1")
            self.assertEqual(len(payload["connections"]), 1)

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_package_backend_bootstrap_writes_manifest_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-workbook-sync-bootstrap-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "package-workbook.xlsx"
            output_dir = tmp / "bootstrap"
            build_minimal_ooxml_workbook(workbook)
            proc = run_pwsh_file(
                "bootstrap",
                "--workbook-path",
                str(workbook),
                "--output-dir",
                str(output_dir),
                "--backend",
                "package",
                timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["backend"], "package")
            manifest = output_dir / "excel-sync.manifest.json"
            tables = output_dir / "workbook_structure" / "tables.json"
            names = output_dir / "workbook_structure" / "names.json"
            cf = output_dir / "workbook_structure" / "conditional_formatting.json"
            pq_query = output_dir / "power_query" / "queries" / "Query1.pq"
            pq_queries = output_dir / "power_query" / "queries.json"
            self.assertTrue(manifest.exists())
            self.assertTrue(tables.exists())
            self.assertTrue(names.exists())
            self.assertTrue(cf.exists())
            self.assertTrue(pq_query.exists())
            self.assertTrue(pq_queries.exists())
            manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertIn("powerQuery", manifest_payload)
            self.assertEqual(manifest_payload["structure"]["tablesPath"], "workbook_structure/tables.json")
            queries_payload = json.loads(pq_queries.read_text(encoding="utf-8"))
            self.assertEqual(queries_payload["queries"][0]["name"], "Query1")

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_pull_falls_back_to_package_parser_for_manifest_bundle(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-workbook-sync-pull-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "package-workbook.xlsx"
            output_dir = tmp / "bundle"
            build_minimal_ooxml_workbook(workbook)

            bootstrap_proc = run_pwsh_file(
                "bootstrap",
                "--workbook-path",
                str(workbook),
                "--output-dir",
                str(output_dir),
                "--backend",
                "package",
                timeout=60,
            )
            self.assertEqual(bootstrap_proc.returncode, 0, bootstrap_proc.stdout + bootstrap_proc.stderr)

            manifest = output_dir / "excel-sync.manifest.json"
            queries_json = output_dir / "power_query" / "queries.json"
            query_file = output_dir / "power_query" / "queries" / "Query1.pq"
            tables_json = output_dir / "workbook_structure" / "tables.json"
            names_json = output_dir / "workbook_structure" / "names.json"
            cf_json = output_dir / "workbook_structure" / "conditional_formatting.json"

            for artifact in [queries_json, query_file, tables_json, names_json, cf_json]:
                artifact.unlink()

            pull_proc = run_pwsh_file(
                "pull",
                "--manifest-path",
                str(manifest),
                "--workbook-path",
                str(workbook),
                timeout=60,
            )
            self.assertEqual(pull_proc.returncode, 0, pull_proc.stdout + pull_proc.stderr)
            self.assertIn("PULL PQ Query1", pull_proc.stdout)
            self.assertIn("PULL TABLES =>", pull_proc.stdout)
            self.assertIn("PULL NAMES =>", pull_proc.stdout)
            self.assertIn("PULL CF =>", pull_proc.stdout)
            self.assertIn("SKIP VBA no VBA artifacts configured", pull_proc.stdout)

            queries_payload = json.loads(queries_json.read_text(encoding="utf-8"))
            tables_payload = json.loads(tables_json.read_text(encoding="utf-8"))
            names_payload = json.loads(names_json.read_text(encoding="utf-8"))
            cf_payload = json.loads(cf_json.read_text(encoding="utf-8"))

            self.assertEqual(queries_payload["queries"][0]["name"], "Query1")
            self.assertTrue(query_file.exists())
            self.assertEqual(tables_payload["tables"][0]["name"], "Table1")
            self.assertEqual(names_payload["names"][0]["name"], "MyValue")
            self.assertEqual(cf_payload["rules"][0]["type"], "expression")

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_roundtrip_reports_read_only_fallback_for_package_only_workbook(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-workbook-sync-roundtrip-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "package-workbook.xlsx"
            output_dir = tmp / "bundle"
            build_minimal_ooxml_workbook(workbook)

            bootstrap_proc = run_pwsh_file(
                "bootstrap",
                "--workbook-path",
                str(workbook),
                "--output-dir",
                str(output_dir),
                "--backend",
                "package",
                timeout=60,
            )
            self.assertEqual(bootstrap_proc.returncode, 0, bootstrap_proc.stdout + bootstrap_proc.stderr)

            manifest = output_dir / "excel-sync.manifest.json"
            proc = run_pwsh_file(
                "roundtrip",
                "--manifest-path",
                str(manifest),
                "--workbook-path",
                str(workbook),
                timeout=60,
            )
            self.assertNotEqual(proc.returncode, 0)
            combined = proc.stdout + proc.stderr
            self.assertIn("Package fallback is currently read-only for push", combined)
            self.assertIn("inspect/query/bootstrap/pull", combined)

    @unittest.skipUnless(HAS_CMD, "cmd not available on this host")
    def test_cmd_launcher_help_is_available(self) -> None:
        proc = subprocess.run(
            ["cmd", "/c", str(CMD), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("Usage:", proc.stdout)
        self.assertNotIn("parameter cannot be found that matches parameter name '-help'", (proc.stdout + proc.stderr).lower())

    def test_posix_launcher_rejects_unknown_subcommand(self) -> None:
        proc = subprocess.run(
            ["sh", str(POSIX), "bogus"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("unknown subcommand", (proc.stdout + proc.stderr).lower())

    def test_posix_launcher_requires_values_for_path_flags(self) -> None:
        proc = subprocess.run(
            ["sh", str(POSIX), "inspect", "--workbook-path"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("missing value", (proc.stdout + proc.stderr).lower())

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_powershell_cli_rejects_sync_without_manifest(self) -> None:
        proc = subprocess.run(
            ["pwsh", "-NoProfile", "-File", str(PS1), "push", "--workbook-path", str(FIXTURE_WORKBOOK)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("manifestpath is required", (proc.stdout + proc.stderr).lower())

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_powershell_cli_negative_query_path_is_concise(self) -> None:
        missing = Path(tempfile.gettempdir()) / "excel-workbook-sync-missing.xlsm"
        proc = run_pwsh_file("query", "--workbook-path", str(missing), "--surface", "tables,names")
        self.assertNotEqual(proc.returncode, 0)
        combined = (proc.stdout + proc.stderr).lower()
        self.assertIn("workbook not found", combined)

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_powershell_cli_accepts_manifest_path_gnu_alias(self) -> None:
        proc = run_pwsh_file("push", "--manifest-path", str(FIXTURE_MANIFEST), "--help")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("parameter cannot be found", (proc.stdout + proc.stderr).lower())

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_powershell_cli_accepts_gnu_flags_for_inspect(self) -> None:
        missing = Path(tempfile.gettempdir()) / "excel-workbook-sync-missing-inspect.xlsx"
        proc = run_pwsh_file("inspect", "--workbook-path", str(missing), "--surface", "tables,names")
        self.assertNotIn("parameter cannot be found", (proc.stdout + proc.stderr).lower())

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_powershell_scripts_parse_cleanly(self) -> None:
        for script in [
            ROOT / "scripts" / "excel-workbook-sync.ps1",
            ROOT / "scripts" / "ExcelSync.Common.ps1",
            ROOT / "scripts" / "sync-excel.ps1",
            ROOT / "scripts" / "sync-excel-powerquery.ps1",
            ROOT / "scripts" / "sync-excel-vba.ps1",
            ROOT / "scripts" / "sync-excel-structure.ps1",
        ]:
            proc = subprocess.run(
                [
                    "pwsh",
                    "-NoProfile",
                    "-Command",
                    (
                        "$errors=$null;$tokens=$null;"
                        "[System.Management.Automation.Language.Parser]::ParseFile("
                        f"(Resolve-Path '{script}'),[ref]$tokens,[ref]$errors)|Out-Null;"
                        "$errors | ForEach-Object { $_.Message + ' @ ' + $_.Extent.Text }"
                    ),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(proc.stdout.strip(), "", proc.stdout + proc.stderr)

    @unittest.skipUnless(os.environ.get("EXCEL_SYNC_LIVE") == "1", "set EXCEL_SYNC_LIVE=1 to run live Excel COM tests")
    def test_live_inspect_returns_counts(self) -> None:
        if not FIXTURE_WORKBOOK.exists():
            self.skipTest("fixture workbook is unavailable")
        proc = subprocess.run(
            [
                "pwsh",
                "-NoProfile",
                "-File",
                str(PS1),
                "inspect",
                "--workbook-path",
                str(FIXTURE_WORKBOOK),
                "--surface",
                "tables,names,project,pq,connections,model",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(Path(payload["workbookPath"]), FIXTURE_WORKBOOK.resolve())
        self.assertIn("counts", payload)
        self.assertIn("project", payload)
        self.assertIn("tables", payload["counts"])
        self.assertIn("names", payload["counts"])
        self.assertIn("pq", payload["counts"])
        self.assertIn("connections", payload["counts"])

    @unittest.skipUnless(os.environ.get("EXCEL_SYNC_LIVE") == "1", "set EXCEL_SYNC_LIVE=1 to run live Excel COM tests")
    def test_live_query_returns_expected_shape(self) -> None:
        if not FIXTURE_WORKBOOK.exists():
            self.skipTest("fixture workbook is unavailable")
        proc = subprocess.run(
            [
                "pwsh",
                "-NoProfile",
                "-File",
                str(PS1),
                "query",
                "--workbook-path",
                str(FIXTURE_WORKBOOK),
                "--surface",
                "tables,names,project,pq,connections,model",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(Path(payload["workbookPath"]), FIXTURE_WORKBOOK.resolve())
        self.assertIsInstance(payload["tables"], list)
        self.assertIsInstance(payload["names"], list)
        self.assertIsInstance(payload["pq"], list)
        self.assertIsInstance(payload["connections"], list)
        self.assertIn("accessible", payload["project"])
        self.assertIn("modelTables", payload["model"])

    @unittest.skipUnless(os.environ.get("EXCEL_SYNC_LIVE") == "1", "set EXCEL_SYNC_LIVE=1 to run live Excel COM tests")
    def test_live_roundtrip_on_temp_workspace_copy(self) -> None:
        if not FIXTURE_WORKBOOK.exists():
            self.skipTest("fixture workbook is unavailable")

        with tempfile.TemporaryDirectory(prefix="excel-workbook-sync-live-") as tmpdir:
            tmp_root = Path(tmpdir) / "workspace"
            shutil.copytree(FIXTURE_DIR, tmp_root)
            manifest = tmp_root / "excel-sync.manifest.json"
            workbook = tmp_root / "tr_upload_template.xlsm"

            proc = subprocess.run(
                [
                    "pwsh",
                    "-NoProfile",
                    "-File",
                    str(PS1),
                    "roundtrip",
                    "--manifest-path",
                    str(manifest),
                    "--workbook-path",
                    str(workbook),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=300,
            )

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("PUSH VBA", proc.stdout)
            self.assertIn("PUSH TABLE", proc.stdout)
            self.assertIn("PUSH NAME", proc.stdout)
            self.assertIn("PULL TABLES", proc.stdout)
            self.assertIn("PULL NAMES", proc.stdout)
            self.assertIn("PULL VBA", proc.stdout)
            self.assertIn("PUSH PQ", proc.stdout)
            self.assertIn("PULL PQ", proc.stdout)

            for artifact in [
                tmp_root / "workbook_structure" / "defaults_tables.json",
                tmp_root / "workbook_structure" / "names.json",
                tmp_root / "workbook_structure" / "conditional_formatting.json",
                tmp_root / "workbook_structure" / "vba_project.json",
                tmp_root / "workbook_structure" / "vba_references.json",
                tmp_root / "power_query" / "queries.json",
                tmp_root / "power_query" / "connections.json",
                tmp_root / "power_query" / "model.json",
            ]:
                payload = json.loads(artifact.read_text(encoding="utf-8"))
                self.assertIsInstance(payload, dict)
                self.assertTrue(payload)


if __name__ == "__main__":
    unittest.main()
