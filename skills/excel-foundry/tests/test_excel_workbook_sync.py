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
POSIX = ROOT / "scripts" / "excel-foundry"
CMD = ROOT / "scripts" / "excel-foundry.cmd"
PS1 = ROOT / "scripts" / "excel-foundry.ps1"
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
        encoding="utf-8",
        errors="replace",
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
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=timeout,
    )


def run_skill_cli(*args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return run_pwsh_file(*args, timeout=timeout)


def save_workbook_as_format(source_path: Path, target_path: Path, file_format: int) -> None:
    proc = run_pwsh(
        dedent(
            f"""
            . '{COMMON}'
            $context = $null
            try {{
                $context = Open-ExcelWorkbook -WorkbookPath '{source_path}' -Visible:$false
                $context.Workbook.SaveAs('{target_path}', {file_format})
            }}
            finally {{
                if ($null -ne $context) {{
                    Close-ExcelWorkbook -Context $context -SaveChanges:$false
                }}
            }}
            """
        ),
        timeout=180,
    )
    if proc.returncode != 0:
        raise AssertionError(proc.stdout + proc.stderr)


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
              <Override PartName="/xl/comments1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.comments+xml"/>
              <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
              <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
              <Override PartName="/docProps/custom.xml" ContentType="application/vnd.openxmlformats-officedocument.custom-properties+xml"/>
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
              <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
              <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
              <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties" Target="docProps/custom.xml"/>
            </Relationships>
            """
        ),
        "xl/workbook.xml": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <calcPr calcMode="auto" fullCalcOnLoad="1"/>
              <workbookProtection lockStructure="1" lockWindows="0"/>
              <sheets>
                <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
              </sheets>
              <definedNames>
                <definedName name="MyValue">Sheet1!$B$2</definedName>
                <definedName name="_xlnm.Print_Area" localSheetId="0">Sheet1!$A$1:$C$3</definedName>
                <definedName name="_xlnm.Print_Titles" localSheetId="0">Sheet1!$1:$1</definedName>
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
              <cols>
                <col min="1" max="1" width="18" customWidth="1"/>
              </cols>
              <sheetData>
                <row r="1" ht="24" customHeight="1">
                  <c r="A1" t="s"><v>0</v></c>
                  <c r="B1" t="s"><v>1</v></c>
                </row>
                <row r="2">
                  <c r="A2" t="s"><v>2</v></c>
                  <c r="B2"><v>1</v></c>
                  <c r="C2"><f>SUM(B2,1)</f><v>2</v></c>
                </row>
              </sheetData>
              <dataValidations count="1">
                <dataValidation type="whole" allowBlank="1" showInputMessage="1" showErrorMessage="1" operator="between" sqref="B2">
                  <formula1>1</formula1>
                  <formula2>10</formula2>
                </dataValidation>
              </dataValidations>
              <conditionalFormatting sqref="B2">
                <cfRule type="expression" priority="1">
                  <formula>B2&gt;0</formula>
                </cfRule>
              </conditionalFormatting>
              <hyperlinks>
                <hyperlink ref="A2" r:id="rId2" tooltip="Go to example"/>
              </hyperlinks>
              <sheetProtection sheet="1" objects="1" scenarios="0"/>
              <pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>
              <pageSetup paperSize="9" orientation="landscape" fitToWidth="1" fitToHeight="0"/>
              <printOptions horizontalCentered="1" verticalCentered="0" gridLines="1"/>
              <headerFooter><oddHeader>&amp;F</oddHeader><oddFooter>Page &amp;P</oddFooter></headerFooter>
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
              <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.com/report" TargetMode="External"/>
              <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="../comments1.xml"/>
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
        "xl/comments1.xml": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <comments xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <authors><author>Excel Foundry</author></authors>
              <commentList>
                <comment ref="B2" authorId="0"><text><r><t>Review this value</t></r></text></comment>
              </commentList>
            </comments>
            """
        ),
        "docProps/core.xml": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/">
              <dc:title>Workbook Fixture</dc:title>
              <dc:subject>Excel Foundry Tests</dc:subject>
            </cp:coreProperties>
            """
        ),
        "docProps/app.xml": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
              <Application>Excel Foundry</Application>
            </Properties>
            """
        ),
        "docProps/custom.xml": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
              <property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="2" name="Environment">
                <vt:lpwstr>test</vt:lpwstr>
              </property>
            </Properties>
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
        self.assertTrue((ROOT / "README.md").exists())
        self.assertTrue(OPENAI_YAML.exists())
        self.assertTrue(POSIX.exists())
        self.assertTrue(CMD.exists())
        self.assertTrue(PS1.exists())
        self.assertTrue(FIXTURE_MANIFEST.exists())
        self.assertTrue(COMMON.exists())
        self.assertTrue(POWERQUERY.exists())
        self.assertTrue((ROOT / "references" / "protocol-audit.md").exists())
        self.assertTrue((ROOT / "references" / "protocol-manifest-sync.md").exists())
        self.assertTrue((ROOT / "references" / "output-contract.md").exists())

    def test_openai_yaml_interface_only(self) -> None:
        content = OPENAI_YAML.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("interface:\n"))
        self.assertNotIn("metadata:", content)
        self.assertIn("matrix-audit", content)

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
        workbook_path = Path(tempfile.gettempdir()) / "excel-foundry-manifestless.xlsm"
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
        with tempfile.TemporaryDirectory(prefix="excel-foundry-legacy-") as tmpdir:
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

    def test_auto_query_prefers_package_for_package_readable_surfaces(self) -> None:
        proc = run_pwsh(
            dedent(
                f"""
                . '{COMMON}'
                function Test-OoxmlPackageWorkbook {{ param([string]$WorkbookPath) return $true }}
                function Open-ExcelWorkbook {{ throw 'excel path should not be used' }}
                function Invoke-PackageWorkbookHelper {{
                    param([string]$Command, [string]$WorkbookPath, [string[]]$Surface)
                    return [pscustomobject]@{{
                        workbookPath = $WorkbookPath
                        backend = 'package'
                        sourceFormat = '.xlsm'
                        workingPath = $WorkbookPath
                        normalization = 'none'
                        warnings = @()
                        capabilities = Get-PackageBackendCapabilities
                        unsupported = @()
                        tables = @([pscustomobject]@{{ name = 'T1' }})
                    }}
                }}
                Get-ExcelWorkbookQuery -WorkbookPath 'dummy.xlsm' -Surface @('tables','formulas','data-validation') -Backend auto |
                    ConvertTo-Json -Compress -Depth 20
                """
            )
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["backend"], "package")
        self.assertEqual(payload["stagesTried"], ["package"])
        self.assertEqual(payload["tables"][0]["name"], "T1")

    def test_structure_script_has_optional_cf_property_guard(self) -> None:
        content = (ROOT / "scripts" / "sync-excel-structure.ps1").read_text(encoding="utf-8")
        self.assertIn('PSObject.Properties["replaceIfFormulaContains"]', content)

    def test_structure_script_rebuilds_cf_per_sheet(self) -> None:
        content = (ROOT / "scripts" / "sync-excel-structure.ps1").read_text(encoding="utf-8")
        self.assertIn("$rulesBySheet", content)
        self.assertIn("Remove-SupportedFormatConditions -TargetRange $worksheet.Cells", content)

    def test_structure_script_uses_bulk_table_writes(self) -> None:
        content = (ROOT / "scripts" / "sync-excel-structure.ps1").read_text(encoding="utf-8")
        self.assertIn("$target.Value2 = $matrix", content)

    def test_common_script_smoke_copies_workspace_recursively(self) -> None:
        content = COMMON.read_text(encoding="utf-8")
        self.assertIn("Copy-Item -LiteralPath $manifestDirectory -Destination $tempWorkspace -Recurse -Force", content)
        self.assertIn('Remove-Item -LiteralPath $tempRoot -Recurse -Force', content)

    def test_common_script_uses_retry_aware_excel_open_and_quit_cleanup(self) -> None:
        content = COMMON.read_text(encoding="utf-8")
        self.assertIn('Invoke-ExcelComWithRetry -Description $openDescription', content)
        self.assertIn("direct-open-readonly-repair", content)
        self.assertIn("direct-open-readonly-extract", content)
        self.assertIn('Invoke-ExcelQuitSafely -Excel $excel -Description "Quitting Excel after failed open" -SwallowErrors', content)
        self.assertIn('Invoke-ExcelQuitSafely -Excel $excel -Description "Quitting Excel"', content)

    def test_mutation_and_com_extract_use_common_workbook_context(self) -> None:
        mutate = (ROOT / "scripts" / "mutate-workbook.ps1").read_text(encoding="utf-8")
        extract = (ROOT / "scripts" / "extract-com.ps1").read_text(encoding="utf-8")
        self.assertIn(". (Join-Path $PSScriptRoot 'ExcelSync.Common.ps1')", mutate)
        self.assertIn("Open-ExcelWorkbook -WorkbookPath $WorkbookPath -Visible:$Visible", mutate)
        self.assertIn("Close-ExcelWorkbook -Context $context -SaveChanges:$saved", mutate)
        self.assertIn(". (Join-Path $PSScriptRoot 'ExcelSync.Common.ps1')", extract)
        self.assertIn("Open-ExcelWorkbook -WorkbookPath $WorkbookPath -Visible:$Visible -ReadOnlyIntent", extract)
        self.assertIn("Close-ExcelWorkbook -Context $context -SaveChanges:$false", extract)

    def test_query_path_uses_read_only_excel_open_intent(self) -> None:
        content = COMMON.read_text(encoding="utf-8")
        self.assertIn("Open-ExcelWorkbook -WorkbookPath $WorkbookPath -Visible:$Visible -ReadOnlyIntent", content)

    def test_common_script_exposes_package_bootstrap_and_surface_aliases(self) -> None:
        content = COMMON.read_text(encoding="utf-8")
        self.assertIn("function Get-NormalizedSurfaceNames", content)
        self.assertIn("function Invoke-ExcelWorkbookBootstrap", content)
        self.assertIn("function Invoke-PackageWorkbookHelper", content)
        self.assertIn("EXCEL_WORKBOOK_SYNC_PYTHON", content)
        self.assertIn("[System.Diagnostics.ProcessStartInfo]::new()", content)
        self.assertIn("$startInfo.ArgumentList.Add", content)
        self.assertIn("WaitForExit($TimeoutSeconds * 1000)", content)
        self.assertIn("Package workbook helper timed out", content)

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_package_helper_timeout_is_behavioral(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-timeout-") as tmpdir:
            tmp = Path(tmpdir)
            fake_python = tmp / "fake-python.cmd"
            fake_python.write_text(
                "@echo off\r\n"
                "powershell -NoProfile -Command \"Start-Sleep -Seconds 5\"\r\n",
                encoding="utf-8",
            )
            workbook = tmp / "package-workbook.xlsx"
            build_minimal_ooxml_workbook(workbook)
            env = os.environ.copy()
            env["EXCEL_WORKBOOK_SYNC_PYTHON"] = str(fake_python)
            proc = subprocess.run(
                [
                    "pwsh",
                    "-NoProfile",
                    "-Command",
                    (
                        f". '{COMMON}'; "
                        f"Invoke-PackageWorkbookHelper -Command inspect -WorkbookPath '{workbook}' -TimeoutSeconds 1 | Out-Null"
                    ),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                env=env,
                timeout=30,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("Package workbook helper timed out", proc.stderr + proc.stdout)

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_common_script_normalizes_excel_formulas_for_comparison(self) -> None:
        proc = run_pwsh(
            dedent(
                f"""
                . '{COMMON}'
                [pscustomobject]@{{
                    left = Normalize-ExcelFormulaForComparison -Formula " =True "
                    right = Normalize-ExcelFormulaForComparison -Formula "= true"
                    multiline = Normalize-ExcelFormulaForComparison -Formula "=IF(A1>0,`r`n TRUE, FALSE)"
                }} | ConvertTo-Json -Compress
                """
            )
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["left"], "=TRUE")
        self.assertEqual(payload["right"], "= TRUE")
        self.assertEqual(payload["multiline"], "=IF(A1>0, TRUE, FALSE)")

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_common_script_matches_conditional_format_rules_semantically(self) -> None:
        proc = run_pwsh(
            dedent(
                f"""
                . '{COMMON}'
                $rule = [pscustomobject]@{{
                    id = 'CF-1'
                    sheet = 'AP_INVOICES_INTERFACE'
                    address = '$C$5:$C$9'
                    type = 'expression'
                    formula = '=TRUE'
                    priority = 9999
                    format = [pscustomobject]@{{
                        interiorColor = '#00ff00'
                    }}
                }}
                $candidate = [pscustomobject]@{{
                    id = 'LIVE'
                    sheet = 'AP_INVOICES_INTERFACE'
                    address = '$C$5:$C$9'
                    type = 'expression'
                    formula = ' =true '
                    priority = 4
                    format = [pscustomobject]@{{
                        interiorColor = '#00FF00'
                        fontColor = '#000000'
                        bold = $true
                    }}
                }}
                [pscustomobject]@{{
                    match = Test-ConditionalFormatRuleSemanticMatch -RuleSpec $rule -Candidate $candidate
                }} | ConvertTo-Json -Compress
                """
            )
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["match"])

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_common_script_resolves_conditional_format_match_by_closest_priority(self) -> None:
        proc = run_pwsh(
            dedent(
                f"""
                . '{COMMON}'
                $rule = [pscustomobject]@{{
                    id = 'CF-1'
                    sheet = 'AP_INVOICES_INTERFACE'
                    address = '$C$5:$C$9'
                    type = 'expression'
                    formula = '=TRUE'
                    priority = 8
                    format = [pscustomobject]@{{ interiorColor = '#00FF00' }}
                }}
                $candidates = @(
                    [pscustomobject]@{{ id='A'; sheet='AP_INVOICES_INTERFACE'; address='$C$5:$C$9'; type='expression'; formula='=TRUE'; priority=3; format=[pscustomobject]@{{ interiorColor = '#00FF00' }} }},
                    [pscustomobject]@{{ id='B'; sheet='AP_INVOICES_INTERFACE'; address='$C$5:$C$9'; type='expression'; formula='=TRUE'; priority=7; format=[pscustomobject]@{{ interiorColor = '#00FF00' }} }}
                )
                $match = Resolve-ConditionalFormatRuleMatch -RuleSpec $rule -Candidates $candidates
                [pscustomobject]@{{ id = $match.id }} | ConvertTo-Json -Compress
                """
            )
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["id"], "B")

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_common_script_reports_ambiguous_conditional_format_matches(self) -> None:
        proc = run_pwsh(
            dedent(
                f"""
                . '{COMMON}'
                $rule = [pscustomobject]@{{
                    id = 'CF-AMBIG'
                    sheet = 'AP_INVOICES_INTERFACE'
                    address = '$C$5:$C$9'
                    type = 'expression'
                    formula = '=TRUE'
                    priority = 8
                    format = [pscustomobject]@{{ interiorColor = '#00FF00' }}
                }}
                $candidates = @(
                    [pscustomobject]@{{ id='A'; sheet='AP_INVOICES_INTERFACE'; address='$C$5:$C$9'; type='expression'; formula='=TRUE'; priority=7; format=[pscustomobject]@{{ interiorColor = '#00FF00' }} }},
                    [pscustomobject]@{{ id='B'; sheet='AP_INVOICES_INTERFACE'; address='$C$5:$C$9'; type='expression'; formula='=TRUE'; priority=9; format=[pscustomobject]@{{ interiorColor = '#00FF00' }} }}
                )
                Resolve-ConditionalFormatRuleMatch -RuleSpec $rule -Candidates $candidates | Out-Null
                """
            )
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("ambiguous", (proc.stdout + proc.stderr).lower())

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
        self.assertIn("inspect|query|push|pull|roundtrip|smoke|refresh|bootstrap|plan|compare|sync", proc.stdout)

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_powershell_cli_help_is_available(self) -> None:
        proc = run_pwsh_file("--help")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("Usage:", proc.stdout)
        self.assertIn("bootstrap", proc.stdout)
        self.assertIn("connection|chart|pivot", proc.stdout)
        self.assertIn("--spec-json JSON", proc.stdout)
        self.assertIn("GNU-style and native PowerShell flags are both accepted.", proc.stdout)

    def test_posix_launcher_translates_gnu_flags_for_powershell_backend(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-posix-") as tmpdir:
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
            self.assertTrue(args[4].endswith("/scripts/excel-foundry.ps1") or args[4].endswith("\\scripts\\excel-foundry.ps1"))
            self.assertEqual(args[5], "inspect")
            self.assertEqual(args[6], "-ManifestPath")
            self.assertTrue(args[7].lower().endswith("test manifest.json"))
            self.assertEqual(args[8], "-WorkbookPath")
            self.assertTrue(args[9].lower().endswith("test workbook.xlsm"))
            self.assertEqual(args[10:], ["-Surface", "tables,names", "-QueryName", "Matched", "-Visible"])

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_package_backend_query_reads_minimal_ooxml_workbook(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-package-") as tmpdir:
            workbook = Path(tmpdir) / "package-workbook.xlsx"
            build_minimal_ooxml_workbook(workbook)
            proc = run_pwsh_file(
                "query",
                "--workbook-path",
                str(workbook),
                "--surface",
                "sheets,tables,names,conditional-formatting,pq,connections,model,formulas,data-validation,protection,charts,pivots",
                "--backend",
                "package",
                timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["backend"], "package")
            self.assertTrue(payload["capabilities"]["canWrite"])
            self.assertTrue(payload["capabilities"]["packageReadable"])
            self.assertEqual(len(payload["sheets"]), 1)
            self.assertEqual(payload["sheets"][0]["name"], "Sheet1")
            self.assertEqual(len(payload["tables"]), 1)
            self.assertEqual(payload["tables"][0]["name"], "Table1")
            self.assertEqual(len(payload["names"]), 1)
            self.assertEqual(payload["names"][0]["name"], "MyValue")
            self.assertEqual(len(payload["cf"]), 1)
            self.assertEqual(len(payload["formulas"]), 1)
            self.assertEqual(payload["formulas"][0]["address"], "C2")
            self.assertEqual(payload["formulas"][0]["formula"], "SUM(B2,1)")
            self.assertEqual(len(payload["dataValidation"]), 1)
            self.assertEqual(payload["dataValidation"][0]["type"], "whole")
            self.assertTrue(payload["protection"]["workbook"]["lockStructure"])
            self.assertEqual(len(payload["protection"]["worksheets"]), 1)
            self.assertTrue(any(item["surface"] == "charts" for item in payload["unsupported"]))
            self.assertEqual(len(payload["pq"]), 1)
            self.assertEqual(payload["pq"][0]["name"], "Query1")
            self.assertEqual(payload["pq"][0]["connectionName"], "Query - Query1")
            self.assertEqual(payload["pq"][0]["loads"][0]["table"], "Table1")
            self.assertEqual(len(payload["connections"]), 1)

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_direct_package_commands_support_core_workbook_ops(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-direct-") as tmpdir:
            workbook = Path(tmpdir) / "package-workbook.xlsx"
            build_minimal_ooxml_workbook(workbook)

            proc = run_pwsh_file("sheet", "list", "--workbook-path", str(workbook), timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["sheets"][0]["name"], "Sheet1")

            proc = run_pwsh_file("sheet", "create", "--workbook-path", str(workbook), "--sheet", "Sheet2", timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

            proc = run_pwsh_file("name", "set", "--workbook-path", str(workbook), "--name", "MyOtherValue", "--refers-to", "Sheet1!$A$2", timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

            proc = run_pwsh_file("cell", "set", "--workbook-path", str(workbook), "--sheet", "Sheet1", "--address", "D4", "--value-json", "\"hello\"", timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

            proc = run_pwsh_file("range", "set", "--workbook-path", str(workbook), "--sheet", "Sheet1", "--range-ref", "E5:F6", "--values-json", "[[1,2],[3,4]]", timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

            proc = run_pwsh_file("cell", "get", "--workbook-path", str(workbook), "--sheet", "Sheet1", "--address", "D4", timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["cell"]["value"], "hello")

            proc = run_pwsh_file("range", "get", "--workbook-path", str(workbook), "--sheet", "Sheet1", "--range-ref", "E5:F6", timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["range"]["values"], [[1, 2], [3, 4]])

            proc = run_pwsh_file("name", "list", "--workbook-path", str(workbook), timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue(any(item["name"] == "MyOtherValue" for item in json.loads(proc.stdout)["names"]))

            proc = run_pwsh_file("table", "read", "--workbook-path", str(workbook), "--table", "Table1", timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["table"]["name"], "Table1")

            proc = run_pwsh_file("query", "list", "--workbook-path", str(workbook), timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["queries"][0]["name"], "Query1")

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_package_backend_bootstrap_writes_manifest_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-bootstrap-") as tmpdir:
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
            sheets = output_dir / "workbook_structure" / "sheets.json"
            tables = output_dir / "workbook_structure" / "tables.json"
            names = output_dir / "workbook_structure" / "names.json"
            cf = output_dir / "workbook_structure" / "conditional_formatting.json"
            formulas = output_dir / "workbook_structure" / "formulas.json"
            data_validation = output_dir / "workbook_structure" / "data_validation.json"
            protection = output_dir / "workbook_structure" / "protection.json"
            charts = output_dir / "workbook_structure" / "charts.json"
            pivots = output_dir / "workbook_structure" / "pivots.json"
            pq_query = output_dir / "power_query" / "queries" / "Query1.pq"
            pq_queries = output_dir / "power_query" / "queries.json"
            self.assertTrue(manifest.exists())
            self.assertTrue(sheets.exists())
            self.assertTrue(tables.exists())
            self.assertTrue(names.exists())
            self.assertTrue(cf.exists())
            self.assertTrue(formulas.exists())
            self.assertTrue(data_validation.exists())
            self.assertTrue(protection.exists())
            self.assertTrue(charts.exists())
            self.assertTrue(pivots.exists())
            self.assertTrue(pq_query.exists())
            self.assertTrue(pq_queries.exists())
            manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertIn("powerQuery", manifest_payload)
            self.assertEqual(manifest_payload["structure"]["sheetsPath"], "workbook_structure/sheets.json")
            self.assertEqual(manifest_payload["structure"]["tablesPath"], "workbook_structure/tables.json")
            self.assertEqual(manifest_payload["structure"]["formulasPath"], "workbook_structure/formulas.json")
            self.assertEqual(manifest_payload["structure"]["dataValidationPath"], "workbook_structure/data_validation.json")
            self.assertEqual(manifest_payload["structure"]["protectionPath"], "workbook_structure/protection.json")
            self.assertEqual(manifest_payload["structure"]["chartsPath"], "workbook_structure/charts.json")
            self.assertEqual(manifest_payload["structure"]["pivotsPath"], "workbook_structure/pivots.json")
            self.assertEqual(manifest_payload["structure"]["workbookPath"], "workbook_structure/workbook.json")
            self.assertEqual(manifest_payload["structure"]["dimensionsPath"], "workbook_structure/dimensions.json")
            self.assertEqual(manifest_payload["structure"]["hyperlinksPath"], "workbook_structure/hyperlinks.json")
            self.assertEqual(manifest_payload["structure"]["commentsPath"], "workbook_structure/comments.json")
            self.assertEqual(manifest_payload["structure"]["printPath"], "workbook_structure/print.json")
            queries_payload = json.loads(pq_queries.read_text(encoding="utf-8"))
            self.assertEqual(queries_payload["queries"][0]["name"], "Query1")

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_workbook_resource_commands_expose_capabilities_and_rich_package_surfaces(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-workbook-resource-") as tmpdir:
            workbook = Path(tmpdir) / "resource.xlsx"
            build_minimal_ooxml_workbook(workbook)

            capabilities_proc = run_pwsh_file("workbook", "capabilities", "--workbook-path", str(workbook), timeout=60)
            self.assertEqual(capabilities_proc.returncode, 0, capabilities_proc.stdout + capabilities_proc.stderr)
            capabilities_payload = json.loads(capabilities_proc.stdout)
            self.assertTrue(capabilities_payload["capabilities"]["package"]["canRead"])
            self.assertIn("hyperlinks", capabilities_payload["capabilities"]["package"]["supportedReadSurfaces"])

            inspect_proc = run_pwsh_file(
                "workbook",
                "inspect",
                "--workbook-path",
                str(workbook),
                "--surface",
                "workbook,dimensions,hyperlinks,comments,print",
                timeout=60,
            )
            self.assertEqual(inspect_proc.returncode, 0, inspect_proc.stdout + inspect_proc.stderr)
            inspect_payload = json.loads(inspect_proc.stdout)
            self.assertEqual(inspect_payload["counts"]["workbook"], 1)
            self.assertEqual(inspect_payload["counts"]["hyperlinks"], 1)
            self.assertEqual(inspect_payload["counts"]["comments"], 1)
            self.assertEqual(inspect_payload["counts"]["dimensionSheets"], 1)
            self.assertEqual(inspect_payload["counts"]["printSheets"], 1)
            self.assertEqual(inspect_payload["workbook"]["properties"]["core"]["title"], "Workbook Fixture")
            self.assertEqual(inspect_payload["workbook"]["calculation"]["mode"], "auto")

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_workbook_create_diff_and_manifest_lifecycle_commands_work(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-workbook-lifecycle-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "created.xlsx"
            create_spec = json.dumps(
                {
                    "title": "Created by Excel Foundry",
                    "subject": "Workbook create test",
                    "sheets": ["Inputs", "Model", "Exports"],
                    "customProperties": {"Environment": "test"},
                }
            )
            create_proc = run_pwsh_file("workbook", "create", "--workbook-path", str(workbook), "--spec-json", create_spec, timeout=60)
            self.assertEqual(create_proc.returncode, 0, create_proc.stdout + create_proc.stderr)
            create_payload = json.loads(create_proc.stdout)
            self.assertEqual(create_payload["counts"]["sheets"], 3)
            self.assertTrue(workbook.exists())

            diff_proc = run_pwsh_file(
                "workbook",
                "diff",
                "--workbook-path",
                str(workbook),
                "--other-workbook-path",
                str(workbook),
                "--surface",
                "workbook,sheets",
                timeout=60,
            )
            self.assertEqual(diff_proc.returncode, 0, diff_proc.stdout + diff_proc.stderr)
            self.assertTrue(json.loads(diff_proc.stdout)["match"])

            bootstrap_dir = tmp / "bootstrap"
            bootstrap_proc = run_pwsh_file("bootstrap", "--workbook-path", str(workbook), "--output-dir", str(bootstrap_dir), timeout=60)
            self.assertEqual(bootstrap_proc.returncode, 0, bootstrap_proc.stdout + bootstrap_proc.stderr)
            manifest = bootstrap_dir / "excel-sync.manifest.json"

            validate_proc = run_pwsh_file("manifest", "validate", "--manifest-path", str(manifest), timeout=60)
            self.assertEqual(validate_proc.returncode, 0, validate_proc.stdout + validate_proc.stderr)
            self.assertTrue(json.loads(validate_proc.stdout)["valid"])

            doctor_proc = run_pwsh_file("manifest", "doctor", "--manifest-path", str(manifest), timeout=60)
            self.assertEqual(doctor_proc.returncode, 0, doctor_proc.stdout + doctor_proc.stderr)
            doctor_payload = json.loads(doctor_proc.stdout)
            self.assertTrue(doctor_payload["valid"])
            self.assertIn("resolved", doctor_payload)

            legacy_manifest = tmp / "legacy-excel-sync.manifest.json"
            legacy_manifest.write_text(
                json.dumps({"workbookPath": workbook.name, "structure": {"sheetsPath": "workbook_structure/sheets.json"}}, indent=2) + "\n",
                encoding="utf-8",
            )
            migrate_proc = run_pwsh_file("manifest", "migrate", "--manifest-path", str(legacy_manifest), timeout=60)
            self.assertEqual(migrate_proc.returncode, 0, migrate_proc.stdout + migrate_proc.stderr)
            migrate_payload = json.loads(migrate_proc.stdout)
            self.assertEqual(migrate_payload["migratedManifest"]["version"], 2)
            self.assertIn("printPath", migrate_payload["migratedManifest"]["structure"])

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_package_backend_inspect_preserves_workbook_paths_with_spaces(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-package-space-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "package workbook with spaces.xlsm"
            build_minimal_ooxml_workbook(workbook)
            proc = run_pwsh_file(
                "inspect",
                "--workbook-path",
                str(workbook),
                "--backend",
                "package",
                timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(Path(payload["workbookPath"]), workbook.resolve())
            self.assertEqual(payload["backend"], "package")

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_package_backend_bootstrap_preserves_workbook_paths_with_spaces(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-bootstrap-space-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "package workbook with spaces.xlsm"
            output_dir = tmp / "bootstrap output with spaces"
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
            self.assertEqual(Path(payload["workbookPath"]), workbook.resolve())
            self.assertTrue((output_dir / "excel-sync.manifest.json").exists())

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_package_backend_plan_reports_per_surface_writeability(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-plan-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "plan.xlsx"
            build_minimal_ooxml_workbook(workbook)
            output_dir = tmp / "bundle"
            bootstrap_proc = run_pwsh_file(
                "bootstrap",
                "--workbook-path",
                str(workbook),
                "--output-dir",
                str(output_dir),
                "--surface",
                "names,formulas,data-validation,protection,pq",
                "--backend",
                "package",
                timeout=60,
            )
            self.assertEqual(bootstrap_proc.returncode, 0, bootstrap_proc.stdout + bootstrap_proc.stderr)
            manifest = output_dir / "excel-sync.manifest.json"

            proc = run_pwsh_file(
                "plan",
                "--manifest-path",
                str(manifest),
                "--surface",
                "names,formulas,data-validation,protection,pq",
                "--mode",
                "push",
                "--sheet",
                "Sheet1",
                "--name",
                "MyValue",
                timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            surfaces = {entry["surface"]: entry for entry in payload["surfaces"]}
            self.assertTrue(surfaces["names"]["canWrite"])
            self.assertTrue(surfaces["formulas"]["canWrite"])
            self.assertTrue(surfaces["data-validation"]["canWrite"])
            self.assertTrue(surfaces["protection"]["canWrite"])
            self.assertFalse(surfaces["pq"]["canWrite"])
            self.assertEqual(payload["selectors"]["sheet"], ["Sheet1"])
            self.assertEqual(payload["selectors"]["name"], ["MyValue"])

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_package_backend_compare_is_per_surface(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-compare-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "compare.xlsx"
            build_minimal_ooxml_workbook(workbook)
            output_dir = tmp / "bundle"
            bootstrap_proc = run_pwsh_file(
                "bootstrap",
                "--workbook-path",
                str(workbook),
                "--output-dir",
                str(output_dir),
                "--surface",
                "names,formulas",
                "--backend",
                "package",
                timeout=60,
            )
            self.assertEqual(bootstrap_proc.returncode, 0, bootstrap_proc.stdout + bootstrap_proc.stderr)
            manifest = output_dir / "excel-sync.manifest.json"

            names_path = output_dir / "workbook_structure" / "names.json"
            names_payload = json.loads(names_path.read_text(encoding="utf-8"))
            names_payload["names"][0]["refersTo"] = "Sheet1!$C$2"
            names_path.write_text(json.dumps(names_payload, indent=2) + "\n", encoding="utf-8")

            proc = run_pwsh_file(
                "compare",
                "--manifest-path",
                str(manifest),
                "--surface",
                "names,formulas",
                timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            surfaces = {entry["surface"]: entry for entry in payload["surfaces"]}
            self.assertFalse(surfaces["names"]["strict"]["match"])
            self.assertIn("MyValue", surfaces["names"]["strict"]["whyUnequal"]["changed"][0])
            self.assertTrue(surfaces["formulas"]["strict"]["match"])

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_package_backend_sync_push_apply_updates_tables(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-sync-tables-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "sync-tables.xlsx"
            build_minimal_ooxml_workbook(workbook)
            output_dir = tmp / "bundle"
            bootstrap_proc = run_pwsh_file(
                "bootstrap",
                "--workbook-path",
                str(workbook),
                "--output-dir",
                str(output_dir),
                "--surface",
                "tables",
                "--backend",
                "package",
                timeout=60,
            )
            self.assertEqual(bootstrap_proc.returncode, 0, bootstrap_proc.stdout + bootstrap_proc.stderr)
            manifest = output_dir / "excel-sync.manifest.json"

            tables_path = output_dir / "workbook_structure" / "tables.json"
            tables_payload = json.loads(tables_path.read_text(encoding="utf-8"))
            tables_payload["tables"][0]["headers"] = ["Label", "Amount"]
            tables_payload["tables"][0]["rows"] = [["Beta", 42], ["Gamma", 99]]
            tables_path.write_text(json.dumps(tables_payload, indent=2) + "\n", encoding="utf-8")

            apply_proc = run_pwsh_file(
                "sync",
                "--manifest-path",
                str(manifest),
                "--surface",
                "tables",
                "--mode",
                "push",
                "--sheet",
                "Sheet1",
                "--table",
                "Table1",
                "--apply",
                timeout=60,
            )
            self.assertEqual(apply_proc.returncode, 0, apply_proc.stdout + apply_proc.stderr)
            apply_payload = json.loads(apply_proc.stdout)
            self.assertEqual(apply_payload["surfaces"][0]["status"], "applied")

            query_proc = subprocess.run(
                [
                    "python",
                    str(ROOT / "scripts" / "excel_workbook_package.py"),
                    "query",
                    "--workbook-path",
                    str(workbook),
                    "--surface",
                    "tables",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=60,
            )
            self.assertEqual(query_proc.returncode, 0, query_proc.stdout + query_proc.stderr)
            query_payload = json.loads(query_proc.stdout)
            self.assertEqual(query_payload["tables"][0]["headers"], ["Label", "Amount"])
            self.assertEqual(query_payload["tables"][0]["rows"], [["Beta", 42], ["Gamma", 99]])

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_package_backend_sync_push_apply_updates_supported_surfaces(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-sync-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "sync.xlsx"
            build_minimal_ooxml_workbook(workbook)
            output_dir = tmp / "bundle"
            bootstrap_proc = run_pwsh_file(
                "bootstrap",
                "--workbook-path",
                str(workbook),
                "--output-dir",
                str(output_dir),
                "--surface",
                "names,formulas,protection",
                "--backend",
                "package",
                timeout=60,
            )
            self.assertEqual(bootstrap_proc.returncode, 0, bootstrap_proc.stdout + bootstrap_proc.stderr)
            manifest = output_dir / "excel-sync.manifest.json"

            names_path = output_dir / "workbook_structure" / "names.json"
            names_payload = json.loads(names_path.read_text(encoding="utf-8"))
            names_payload["names"][0]["refersTo"] = "Sheet1!$C$2"
            names_path.write_text(json.dumps(names_payload, indent=2) + "\n", encoding="utf-8")

            formulas_path = output_dir / "workbook_structure" / "formulas.json"
            formulas_payload = json.loads(formulas_path.read_text(encoding="utf-8"))
            formulas_payload["formulas"][0]["formula"] = "SUM(B2,5)"
            formulas_payload["formulas"][0]["value"] = 6
            formulas_path.write_text(json.dumps(formulas_payload, indent=2) + "\n", encoding="utf-8")

            protection_path = output_dir / "workbook_structure" / "protection.json"
            protection_payload = json.loads(protection_path.read_text(encoding="utf-8"))
            protection_payload["worksheets"][0]["objects"] = False
            protection_path.write_text(json.dumps(protection_payload, indent=2) + "\n", encoding="utf-8")

            dry_run = run_pwsh_file(
                "sync",
                "--manifest-path",
                str(manifest),
                "--surface",
                "names,formulas,protection",
                "--mode",
                "push",
                "--sheet",
                "Sheet1",
                "--name",
                "MyValue",
                timeout=60,
            )
            self.assertEqual(dry_run.returncode, 0, dry_run.stdout + dry_run.stderr)
            dry_payload = json.loads(dry_run.stdout)
            self.assertTrue(all(entry["status"] == "dry-run" for entry in dry_payload["surfaces"]))

            apply_proc = run_pwsh_file(
                "sync",
                "--manifest-path",
                str(manifest),
                "--surface",
                "names,formulas,protection",
                "--mode",
                "push",
                "--sheet",
                "Sheet1",
                "--name",
                "MyValue",
                "--apply",
                timeout=60,
            )
            self.assertEqual(apply_proc.returncode, 0, apply_proc.stdout + apply_proc.stderr)
            apply_payload = json.loads(apply_proc.stdout)
            self.assertTrue(all(entry["status"] == "applied" for entry in apply_payload["surfaces"]))

            query_proc = subprocess.run(
                [
                    "python",
                    str(ROOT / "scripts" / "excel_workbook_package.py"),
                    "query",
                    "--workbook-path",
                    str(workbook),
                    "--surface",
                    "names,formulas,protection",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=60,
            )
            self.assertEqual(query_proc.returncode, 0, query_proc.stdout + query_proc.stderr)
            query_payload = json.loads(query_proc.stdout)
            self.assertEqual(query_payload["names"][0]["refersTo"], "Sheet1!$C$2")
            self.assertEqual(query_payload["formulas"][0]["formula"], "SUM(B2,5)")
            self.assertFalse(query_payload["protection"]["worksheets"][0]["objects"])
            baseline = output_dir / ".excel-sync" / "state" / "sync" / "names" / "baseline.json"
            self.assertTrue(baseline.exists())

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_package_backend_sync_push_apply_updates_workbook_adjacent_surfaces(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-sync-meta-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "sync-meta.xlsx"
            build_minimal_ooxml_workbook(workbook)
            output_dir = tmp / "bundle"
            bootstrap_proc = run_pwsh_file(
                "bootstrap",
                "--workbook-path",
                str(workbook),
                "--output-dir",
                str(output_dir),
                "--surface",
                "workbook,dimensions,hyperlinks,comments,print",
                "--backend",
                "package",
                timeout=60,
            )
            self.assertEqual(bootstrap_proc.returncode, 0, bootstrap_proc.stdout + bootstrap_proc.stderr)
            manifest = output_dir / "excel-sync.manifest.json"

            workbook_json = output_dir / "workbook_structure" / "workbook.json"
            workbook_payload = json.loads(workbook_json.read_text(encoding="utf-8"))
            workbook_payload["workbook"]["calculation"]["mode"] = "manual"
            workbook_payload["workbook"]["properties"]["custom"]["Environment"] = "prod"
            workbook_json.write_text(json.dumps(workbook_payload, indent=2) + "\n", encoding="utf-8")

            dimensions_json = output_dir / "workbook_structure" / "dimensions.json"
            dimensions_payload = json.loads(dimensions_json.read_text(encoding="utf-8"))
            dimensions_payload["sheets"][0]["rows"][0]["height"] = 30
            dimensions_payload["sheets"][0]["columns"][0]["width"] = 25
            dimensions_json.write_text(json.dumps(dimensions_payload, indent=2) + "\n", encoding="utf-8")

            hyperlinks_json = output_dir / "workbook_structure" / "hyperlinks.json"
            hyperlinks_payload = json.loads(hyperlinks_json.read_text(encoding="utf-8"))
            hyperlinks_payload["hyperlinks"][0]["target"] = "https://example.com/updated"
            hyperlinks_json.write_text(json.dumps(hyperlinks_payload, indent=2) + "\n", encoding="utf-8")

            comments_json = output_dir / "workbook_structure" / "comments.json"
            comments_payload = json.loads(comments_json.read_text(encoding="utf-8"))
            comments_payload["comments"][0]["text"] = "Updated review note"
            comments_json.write_text(json.dumps(comments_payload, indent=2) + "\n", encoding="utf-8")

            print_json = output_dir / "workbook_structure" / "print.json"
            print_payload = json.loads(print_json.read_text(encoding="utf-8"))
            print_payload["sheets"][0]["printArea"] = "Sheet1!$A$1:$B$2"
            print_payload["sheets"][0]["margins"]["left"] = "1"
            print_payload["sheets"][0]["headerFooter"]["oddHeader"] = "&F - Updated"
            print_json.write_text(json.dumps(print_payload, indent=2) + "\n", encoding="utf-8")

            apply_proc = run_pwsh_file(
                "sync",
                "--manifest-path",
                str(manifest),
                "--surface",
                "workbook,dimensions,hyperlinks,comments,print",
                "--mode",
                "push",
                "--sheet",
                "Sheet1",
                "--apply",
                timeout=60,
            )
            self.assertEqual(apply_proc.returncode, 0, apply_proc.stdout + apply_proc.stderr)
            apply_payload = json.loads(apply_proc.stdout)
            self.assertTrue(all(entry["status"] == "applied" for entry in apply_payload["surfaces"]))

            query_proc = subprocess.run(
                [
                    "python",
                    str(ROOT / "scripts" / "excel_workbook_package.py"),
                    "query",
                    "--workbook-path",
                    str(workbook),
                    "--surface",
                    "workbook,dimensions,hyperlinks,comments,print",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=60,
            )
            self.assertEqual(query_proc.returncode, 0, query_proc.stdout + query_proc.stderr)
            query_payload = json.loads(query_proc.stdout)
            self.assertEqual(query_payload["workbook"]["calculation"]["mode"], "manual")
            self.assertEqual(query_payload["workbook"]["properties"]["custom"]["Environment"], "prod")
            self.assertEqual(query_payload["dimensions"]["sheets"][0]["rows"][0]["height"], 30.0)
            self.assertEqual(query_payload["dimensions"]["sheets"][0]["columns"][0]["width"], 25.0)
            self.assertEqual(query_payload["hyperlinks"][0]["target"], "https://example.com/updated")
            self.assertEqual(query_payload["comments"][0]["text"], "Updated review note")
            self.assertEqual(query_payload["print"]["sheets"][0]["printArea"], "Sheet1!$A$1:$B$2")
            self.assertEqual(query_payload["print"]["sheets"][0]["margins"]["left"], "1")
            self.assertEqual(query_payload["print"]["sheets"][0]["headerFooter"]["oddHeader"], "&F - Updated")

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_pull_falls_back_to_package_parser_for_manifest_bundle(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-pull-") as tmpdir:
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
            sheets_json = output_dir / "workbook_structure" / "sheets.json"
            tables_json = output_dir / "workbook_structure" / "tables.json"
            names_json = output_dir / "workbook_structure" / "names.json"
            cf_json = output_dir / "workbook_structure" / "conditional_formatting.json"
            formulas_json = output_dir / "workbook_structure" / "formulas.json"
            data_validation_json = output_dir / "workbook_structure" / "data_validation.json"
            protection_json = output_dir / "workbook_structure" / "protection.json"
            charts_json = output_dir / "workbook_structure" / "charts.json"
            pivots_json = output_dir / "workbook_structure" / "pivots.json"

            for artifact in [queries_json, query_file, sheets_json, tables_json, names_json, cf_json, formulas_json, data_validation_json, protection_json, charts_json, pivots_json]:
                artifact.unlink()

            pull_proc = run_pwsh_file(
                "pull",
                "--manifest-path",
                str(manifest),
                "--workbook-path",
                str(workbook),
                timeout=120,
            )
            self.assertEqual(pull_proc.returncode, 0, pull_proc.stdout + pull_proc.stderr)
            self.assertIn("PULL PQ Query1", pull_proc.stdout)
            self.assertIn("PULL TABLES =>", pull_proc.stdout)
            self.assertIn("PULL NAMES =>", pull_proc.stdout)
            self.assertIn("PULL CF =>", pull_proc.stdout)
            self.assertIn("PULL FORMULAS =>", pull_proc.stdout)
            self.assertIn("PULL DATA-VALIDATION =>", pull_proc.stdout)
            self.assertIn("PULL PROTECTION =>", pull_proc.stdout)
            self.assertIn("PULL CHARTS =>", pull_proc.stdout)
            self.assertIn("PULL PIVOTS =>", pull_proc.stdout)
            self.assertIn("SKIP VBA no VBA artifacts configured", pull_proc.stdout)

            queries_payload = json.loads(queries_json.read_text(encoding="utf-8"))
            sheets_payload = json.loads(sheets_json.read_text(encoding="utf-8"))
            tables_payload = json.loads(tables_json.read_text(encoding="utf-8"))
            names_payload = json.loads(names_json.read_text(encoding="utf-8"))
            cf_payload = json.loads(cf_json.read_text(encoding="utf-8"))
            formulas_payload = json.loads(formulas_json.read_text(encoding="utf-8"))
            data_validation_payload = json.loads(data_validation_json.read_text(encoding="utf-8"))
            protection_payload = json.loads(protection_json.read_text(encoding="utf-8"))
            charts_payload = json.loads(charts_json.read_text(encoding="utf-8"))
            pivots_payload = json.loads(pivots_json.read_text(encoding="utf-8"))

            self.assertEqual(queries_payload["queries"][0]["name"], "Query1")
            self.assertEqual(sheets_payload["sheets"][0]["name"], "Sheet1")
            self.assertTrue(query_file.exists())
            self.assertEqual(tables_payload["tables"][0]["name"], "Table1")
            self.assertEqual(names_payload["names"][0]["name"], "MyValue")
            self.assertEqual(cf_payload["rules"][0]["type"], "expression")
            self.assertEqual(formulas_payload["formulas"][0]["address"], "C2")
            self.assertEqual(data_validation_payload["rules"][0]["address"], "B2")
            self.assertTrue(protection_payload["workbook"]["lockStructure"])
            self.assertEqual(charts_payload["charts"], [])
            self.assertEqual(pivots_payload["pivots"], [])

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_package_backend_inspect_reports_capabilities_and_new_counts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-package-inspect-") as tmpdir:
            workbook = Path(tmpdir) / "package-workbook.xlsx"
            build_minimal_ooxml_workbook(workbook)
            proc = run_pwsh_file(
                "inspect",
                "--workbook-path",
                str(workbook),
                "--surface",
                "sheets,tables,names,conditional-formatting,pq,connections,model,formulas,data-validation,protection,charts,pivots,project",
                "--backend",
                "package",
                timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["counts"]["sheets"], 1)
            self.assertEqual(payload["counts"]["formulas"], 1)
            self.assertEqual(payload["counts"]["dataValidation"], 1)
            self.assertEqual(payload["counts"]["protectedSheets"], 1)
            self.assertEqual(payload["counts"]["workbookProtection"], 1)
            self.assertEqual(payload["counts"]["charts"], 0)
            self.assertEqual(payload["counts"]["pivots"], 0)
            self.assertTrue(payload["capabilities"]["canWrite"])
            self.assertTrue(any(item["surface"] == "charts" for item in payload["unsupported"]))
            self.assertTrue(any(item["surface"] == "project" for item in payload["unsupported"]))

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_roundtrip_reports_read_only_fallback_for_package_only_workbook(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-roundtrip-") as tmpdir:
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
            normalized = " ".join(combined.split())
            self.assertIn("Package fallback is currently", normalized)
            self.assertIn("read-only for push", normalized)
            self.assertIn("inspect/query/bootstrap/pull", normalized)

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

    def test_python_cli_help_mentions_matrix_audit(self) -> None:
        proc = subprocess.run(
            ["python", str(ROOT / "scripts" / "excel_workbook_sync.py"), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("matrix-audit", proc.stdout)

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
        missing = Path(tempfile.gettempdir()) / "excel-foundry-missing.xlsm"
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
        missing = Path(tempfile.gettempdir()) / "excel-foundry-missing-inspect.xlsx"
        proc = run_pwsh_file("inspect", "--workbook-path", str(missing), "--surface", "tables,names")
        self.assertNotIn("parameter cannot be found", (proc.stdout + proc.stderr).lower())

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_powershell_cli_requires_workbook_path_for_advanced_direct_commands(self) -> None:
        proc = run_pwsh_file("query", "list")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("require --workbook-path", (proc.stdout + proc.stderr).lower())

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_powershell_cli_accepts_new_workbook_lifecycle_actions(self) -> None:
        proc = run_pwsh_file("workbook", "compatibility", "--workbook-path", str(FIXTURE_WORKBOOK), "--target-format", "csv", "--help")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        combined = proc.stdout + proc.stderr
        self.assertIn("Usage:", combined)
        self.assertNotIn("unknown action", combined.lower())

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_powershell_cli_accepts_workbook_link_and_safe_export_actions(self) -> None:
        proc = run_pwsh_file("workbook", "links", "--workbook-path", str(FIXTURE_WORKBOOK), "--help")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        combined = proc.stdout + proc.stderr
        self.assertIn("Usage:", combined)
        self.assertNotIn("unknown action", combined.lower())

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_powershell_cli_requires_target_for_workbook_compatibility(self) -> None:
        proc = run_pwsh_file("workbook", "compatibility", "--workbook-path", str(FIXTURE_WORKBOOK))
        self.assertNotEqual(proc.returncode, 0)
        combined = " ".join((proc.stdout + proc.stderr).lower().split())
        self.assertIn("workbook compatibility", combined)
        self.assertIn("--target-path", combined)
        self.assertIn("--target-format", combined)

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_powershell_cli_requires_target_for_workbook_safe_export(self) -> None:
        proc = run_pwsh_file("workbook", "safe-export", "--workbook-path", str(FIXTURE_WORKBOOK))
        self.assertNotEqual(proc.returncode, 0)
        combined = " ".join((proc.stdout + proc.stderr).lower().split())
        self.assertIn("workbook safe-export", combined)
        self.assertIn("--target-path", combined)
        self.assertIn("--target-format", combined)

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_resolve_excel_save_format_supports_major_target_formats(self) -> None:
        proc = run_pwsh(
            dedent(
                f"""
                . '{COMMON}'
                $formats = @('xlsx','xlsm','xlsb','xls','csv','txt','ods') | ForEach-Object {{
                    Resolve-ExcelSaveFormatSpec -SourcePath 'C:\\temp\\book.xlsx' -TargetFormat $_
                }}
                $formats | Select-Object format,extension,fileFormat,flatText,singleSheetOnly,macroContainer,openDocument | ConvertTo-Json -Compress -Depth 20
                """
            )
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        formats = {entry["format"]: entry for entry in payload}
        self.assertEqual(formats["xlsx"]["fileFormat"], 51)
        self.assertEqual(formats["xlsm"]["fileFormat"], 52)
        self.assertEqual(formats["xlsb"]["fileFormat"], 50)
        self.assertEqual(formats["xls"]["fileFormat"], 56)
        self.assertEqual(formats["csv"]["fileFormat"], 62)
        self.assertEqual(formats["txt"]["fileFormat"], 20)
        self.assertEqual(formats["ods"]["fileFormat"], 60)
        self.assertTrue(formats["csv"]["flatText"])
        self.assertTrue(formats["csv"]["singleSheetOnly"])
        self.assertTrue(formats["xlsm"]["macroContainer"])
        self.assertTrue(formats["ods"]["openDocument"])

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_workbook_compatibility_report_flags_flat_export_losses(self) -> None:
        proc = run_pwsh(
            dedent(
                f"""
                . '{COMMON}'
                $inspection = [pscustomobject]@{{
                    workbookPath = 'C:\\temp\\report.xlsm'
                    sourceFormat = '.xlsm'
                    workbook = [pscustomobject]@{{
                        hasVbaProject = $true
                        hasExternalLinks = $true
                        properties = [pscustomobject]@{{
                            custom = [pscustomobject]@{{ Environment = 'test' }}
                        }}
                    }}
                    counts = [pscustomobject]@{{
                        sheets = 3
                        tables = 1
                        names = 2
                        cf = 1
                        pq = 1
                        connections = 1
                        modelTables = 1
                        vba = 1
                        references = 0
                        formulas = 12
                        dataValidation = 1
                        protectedSheets = 0
                        workbookProtection = 0
                        charts = 1
                        pivots = 1
                        hyperlinks = 2
                        comments = 4
                        dimensionSheets = 1
                        printSheets = 1
                    }}
                    sheets = @(
                        [pscustomobject]@{{ name = 'Visible'; visibility = 'visible' }},
                        [pscustomobject]@{{ name = 'Hidden'; visibility = 'hidden' }}
                    )
                }}
                Get-WorkbookCompatibilityReport -InspectionPayload $inspection -TargetFormat 'csv' | ConvertTo-Json -Compress -Depth 20
                """
            )
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["targetFormat"], "csv")
        self.assertTrue(payload["heuristic"])
        self.assertEqual(payload["overallRisk"], "high")
        messages = " ".join(item["message"] for item in payload["findings"])
        self.assertIn("one worksheet", messages.lower())
        self.assertIn("formulas will be written as current displayed values", messages.lower())
        self.assertIn("power query definitions", messages.lower())
        self.assertIn("charts are lost", messages.lower())

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_workbook_document_inspection_reports_manual_findings_without_excel(self) -> None:
        proc = run_pwsh(
            dedent(
                f"""
                . '{COMMON}'
                $inspection = [pscustomobject]@{{
                    workbook = [pscustomobject]@{{
                        hasExternalLinks = $true
                        properties = [pscustomobject]@{{
                            custom = [pscustomobject]@{{ Owner = 'Finance'; Environment = 'Test' }}
                        }}
                    }}
                    counts = [pscustomobject]@{{
                        comments = 2
                        hyperlinks = 3
                    }}
                    sheets = @(
                        [pscustomobject]@{{ name = 'Input'; visibility = 'visible' }},
                        [pscustomobject]@{{ name = 'Staging'; visibility = 'veryHidden' }}
                    )
                }}
                $fakeWorkbook = [pscustomobject]@{{}}
                $fakeWorkbook | Add-Member -MemberType NoteProperty -Name DocumentInspectors -Value $null
                Invoke-WorkbookDocumentInspection -Workbook $fakeWorkbook -InspectionPayload $inspection | ConvertTo-Json -Compress -Depth 20
                """
            )
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        manual = " ".join(item["message"] for item in payload["manualFindings"])
        self.assertIn("comment", manual.lower())
        self.assertIn("custom document properties", manual.lower())
        self.assertIn("hidden or very-hidden sheets", manual.lower())
        self.assertIn("external links", manual.lower())

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_workbook_link_inventory_helper_reads_excel_and_ole_links(self) -> None:
        proc = run_pwsh(
            dedent(
                f"""
                . '{COMMON}'
                $fakeWorkbook = [pscustomobject]@{{}}
                $fakeWorkbook | Add-Member -MemberType ScriptMethod -Name LinkSources -Value {{
                    param($typeId)
                    switch ($typeId) {{
                        1 {{ return @('C:\\legacy\\source.xlsx', 'C:\\legacy\\other.xlsx') }}
                        2 {{ return @('OLEDB;Provider=SQLOLEDB;Data Source=warehouse') }}
                        default {{ return $null }}
                    }}
                }}
                Get-WorkbookLinkInventory -Workbook $fakeWorkbook | ConvertTo-Json -Compress -Depth 20
                """
            )
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(len(payload), 3)
        types = {item["type"] for item in payload}
        self.assertEqual(types, {"excel", "ole"})

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_workbook_break_links_helper_breaks_selected_links(self) -> None:
        proc = run_pwsh(
            dedent(
                f"""
                . '{COMMON}'
                $state = [ordered]@{{
                    links = @(
                        [pscustomobject]@{{ name = 'C:\\source\\a.xlsx'; typeId = 1 }},
                        [pscustomobject]@{{ name = 'C:\\source\\b.xlsx'; typeId = 1 }},
                        [pscustomobject]@{{ name = 'OLEDB;Provider=X'; typeId = 2 }}
                    )
                }}
                $fakeWorkbook = [pscustomobject]@{{}}
                $fakeWorkbook | Add-Member -MemberType ScriptMethod -Name LinkSources -Value {{
                    param($typeId)
                    return @($state.links | Where-Object {{ [int]$_.typeId -eq [int]$typeId }} | ForEach-Object {{ $_.name }})
                }}
                $fakeWorkbook | Add-Member -MemberType ScriptMethod -Name BreakLink -Value {{
                    param($name, $typeId)
                    $state.links = @($state.links | Where-Object {{ $_.name -ne $name }})
                }}
                $result = Invoke-WorkbookBreakLinks -Workbook $fakeWorkbook -Names @('C:\\source\\b.xlsx')
                [pscustomobject]@{{
                    broken = @($result.broken)
                    remaining = @($result.remaining)
                }} | ConvertTo-Json -Compress -Depth 20
                """
            )
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["broken"][0]["name"], "C:\\source\\b.xlsx")
        remaining_names = {item["name"] for item in payload["remaining"]}
        self.assertIn("C:\\source\\a.xlsx", remaining_names)
        self.assertNotIn("C:\\source\\b.xlsx", remaining_names)

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_remove_document_info_helper_reports_results(self) -> None:
        proc = run_pwsh(
            dedent(
                f"""
                . '{COMMON}'
                $fakeWorkbook = [pscustomobject]@{{}}
                $fakeWorkbook | Add-Member -MemberType ScriptMethod -Name RemoveDocumentInformation -Value {{
                    param($typeId)
                }}
                Invoke-WorkbookRemoveDocumentInfo -Workbook $fakeWorkbook -Types @(99, 5) | ConvertTo-Json -Compress -Depth 20
                """
            )
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual([item["typeId"] for item in payload], [99, 5])
        self.assertTrue(all(item["removed"] for item in payload))

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_powershell_scripts_parse_cleanly(self) -> None:
        for script in [
            ROOT / "scripts" / "excel-foundry.ps1",
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
            encoding="utf-8",
            errors="replace",
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
            encoding="utf-8",
            errors="replace",
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

        with tempfile.TemporaryDirectory(prefix="excel-foundry-live-") as tmpdir:
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
                encoding="utf-8",
                errors="replace",
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

    @unittest.skipUnless(os.environ.get("EXCEL_SYNC_LIVE") == "1", "set EXCEL_SYNC_LIVE=1 to run live Excel COM tests")
    def test_live_vba_push_then_pull_roundtrips_module_change(self) -> None:
        if not FIXTURE_WORKBOOK.exists():
            self.skipTest("fixture workbook is unavailable")

        with tempfile.TemporaryDirectory(prefix="excel-foundry-live-vba-") as tmpdir:
            tmp_root = Path(tmpdir) / "workspace"
            shutil.copytree(FIXTURE_DIR, tmp_root)
            manifest = tmp_root / "excel-sync.manifest.json"
            workbook = tmp_root / "tr_upload_template.xlsm"
            module_path = tmp_root / "macros" / "modules" / "modAPSync.vba"

            original = module_path.read_text(encoding="utf-8")
            marker = "' LIVE_VBA_PUSH_MARKER"
            module_path.write_text(original + ("\n" if not original.endswith("\n") else "") + marker + "\n", encoding="utf-8")

            push_proc = run_skill_cli(
                "push",
                "--manifest-path",
                str(manifest),
                "--workbook-path",
                str(workbook),
                timeout=300,
            )
            self.assertEqual(push_proc.returncode, 0, push_proc.stdout + push_proc.stderr)
            self.assertIn("PUSH VBA modAPSync", push_proc.stdout)

            module_path.write_text(original, encoding="utf-8")

            pull_proc = run_skill_cli(
                "pull",
                "--manifest-path",
                str(manifest),
                "--workbook-path",
                str(workbook),
                timeout=300,
            )
            self.assertEqual(pull_proc.returncode, 0, pull_proc.stdout + pull_proc.stderr)
            self.assertIn(marker, module_path.read_text(encoding="utf-8"))

    @unittest.skipUnless(os.environ.get("EXCEL_SYNC_LIVE") == "1", "set EXCEL_SYNC_LIVE=1 to run live Excel COM tests")
    def test_live_cf_push_then_pull_roundtrips_new_rule(self) -> None:
        if not FIXTURE_WORKBOOK.exists():
            self.skipTest("fixture workbook is unavailable")

        with tempfile.TemporaryDirectory(prefix="excel-foundry-live-cf-") as tmpdir:
            tmp_root = Path(tmpdir) / "workspace"
            shutil.copytree(FIXTURE_DIR, tmp_root)
            manifest = tmp_root / "excel-sync.manifest.json"
            workbook = tmp_root / "tr_upload_template.xlsm"
            cf_path = tmp_root / "workbook_structure" / "conditional_formatting.json"

            artifact = json.loads(cf_path.read_text(encoding="utf-8"))
            artifact["rules"].append(
                {
                    "id": "CF-LIVE-TEST-0001",
                    "sheet": "AP_INVOICES_INTERFACE",
                    "address": "$C$5:$C$9",
                    "formula": "=TRUE",
                    "priority": 9999,
                    "stopIfTrue": False,
                    "format": {
                        "interiorColor": "#00FF00",
                        "fontColor": "#000000",
                        "bold": True,
                    },
                }
            )
            cf_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")

            push_proc = run_skill_cli(
                "push",
                "--manifest-path",
                str(manifest),
                "--workbook-path",
                str(workbook),
                timeout=300,
            )
            self.assertEqual(push_proc.returncode, 0, push_proc.stdout + push_proc.stderr)
            self.assertIn("PUSH CF CF-LIVE-TEST-0001", push_proc.stdout)

            baseline = json.loads((FIXTURE_DIR / "workbook_structure" / "conditional_formatting.json").read_text(encoding="utf-8"))
            cf_path.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")

            pull_proc = run_skill_cli(
                "pull",
                "--manifest-path",
                str(manifest),
                "--workbook-path",
                str(workbook),
                timeout=300,
            )
            self.assertEqual(pull_proc.returncode, 0, pull_proc.stdout + pull_proc.stderr)
            pulled = json.loads(cf_path.read_text(encoding="utf-8"))
            self.assertTrue(
                any(
                    rule.get("sheet") == "AP_INVOICES_INTERFACE"
                    and rule.get("address") == "$C$5:$C$9"
                    and rule.get("formula") == "=TRUE"
                    for rule in pulled["rules"]
                )
            )

    @unittest.skipUnless(os.environ.get("EXCEL_SYNC_LIVE") == "1", "set EXCEL_SYNC_LIVE=1 to run live Excel COM tests")
    def test_live_powerquery_push_then_pull_roundtrips_formula_change(self) -> None:
        if not FIXTURE_WORKBOOK.exists():
            self.skipTest("fixture workbook is unavailable")

        with tempfile.TemporaryDirectory(prefix="excel-foundry-live-pq-") as tmpdir:
            tmp_root = Path(tmpdir) / "workspace"
            shutil.copytree(FIXTURE_DIR, tmp_root)
            manifest = tmp_root / "excel-sync.manifest.json"
            workbook = tmp_root / "tr_upload_template.xlsm"
            query_path = tmp_root / "power_query" / "queries" / "Matched.pq"

            original = query_path.read_text(encoding="utf-8")
            marker = "// LIVE_PQ_PUSH_MARKER"
            query_path.write_text(marker + "\n" + original, encoding="utf-8")

            push_proc = run_skill_cli(
                "push",
                "--manifest-path",
                str(manifest),
                "--workbook-path",
                str(workbook),
                timeout=300,
            )
            self.assertEqual(push_proc.returncode, 0, push_proc.stdout + push_proc.stderr)
            self.assertIn("PUSH PQ Matched", push_proc.stdout)

            query_path.write_text(original, encoding="utf-8")

            pull_proc = run_skill_cli(
                "pull",
                "--manifest-path",
                str(manifest),
                "--workbook-path",
                str(workbook),
                timeout=300,
            )
            self.assertEqual(pull_proc.returncode, 0, pull_proc.stdout + pull_proc.stderr)
            self.assertIn(marker, query_path.read_text(encoding="utf-8"))

    @unittest.skipUnless(os.environ.get("EXCEL_SYNC_LIVE") == "1", "set EXCEL_SYNC_LIVE=1 to run live Excel COM tests")
    def test_live_direct_table_commands_roundtrip(self) -> None:
        if not FIXTURE_WORKBOOK.exists():
            self.skipTest("fixture workbook is unavailable")

        with tempfile.TemporaryDirectory(prefix="excel-foundry-live-direct-table-") as tmpdir:
            workbook = Path(tmpdir) / "direct-table.xlsm"
            shutil.copy2(FIXTURE_WORKBOOK, workbook)
            create_spec = json.dumps(
                {
                    "sheet": "AP_INVOICES_INTERFACE",
                    "name": "LIVE_DIRECT_TABLE",
                    "topLeft": "Z1",
                    "headers": ["Code", "Amount"],
                    "rows": [["A100", 10], ["B200", 20]],
                }
            )
            update_spec = json.dumps(
                {
                    "sheet": "AP_INVOICES_INTERFACE",
                    "name": "LIVE_DIRECT_TABLE",
                    "topLeft": "Z1",
                    "headers": ["Code", "Amount", "Flag"],
                    "rows": [["A100", 10, True]],
                }
            )

            create_proc = run_skill_cli("table", "create", "--workbook-path", str(workbook), "--spec-json", create_spec, timeout=300)
            self.assertEqual(create_proc.returncode, 0, create_proc.stdout + create_proc.stderr)
            self.assertEqual(json.loads(create_proc.stdout)["table"]["name"], "LIVE_DIRECT_TABLE")

            get_proc = run_skill_cli("table", "get", "--workbook-path", str(workbook), "--table", "LIVE_DIRECT_TABLE", timeout=300)
            self.assertEqual(get_proc.returncode, 0, get_proc.stdout + get_proc.stderr)
            self.assertEqual(json.loads(get_proc.stdout)["table"]["sheet"], "AP_INVOICES_INTERFACE")

            update_proc = run_skill_cli("table", "update", "--workbook-path", str(workbook), "--spec-json", update_spec, timeout=300)
            self.assertEqual(update_proc.returncode, 0, update_proc.stdout + update_proc.stderr)
            self.assertEqual(len(json.loads(update_proc.stdout)["table"]["headers"]), 3)

            delete_proc = run_skill_cli("table", "delete", "--workbook-path", str(workbook), "--table", "LIVE_DIRECT_TABLE", timeout=300)
            self.assertEqual(delete_proc.returncode, 0, delete_proc.stdout + delete_proc.stderr)
            self.assertTrue(json.loads(delete_proc.stdout)["deleted"])

    @unittest.skipUnless(os.environ.get("EXCEL_SYNC_LIVE") == "1", "set EXCEL_SYNC_LIVE=1 to run live Excel COM tests")
    def test_live_direct_query_and_connection_commands_roundtrip(self) -> None:
        if not FIXTURE_WORKBOOK.exists():
            self.skipTest("fixture workbook is unavailable")

        with tempfile.TemporaryDirectory(prefix="excel-foundry-live-direct-query-") as tmpdir:
            workbook = Path(tmpdir) / "direct-query.xlsm"
            shutil.copy2(FIXTURE_WORKBOOK, workbook)
            spec = json.dumps(
                {
                    "name": "LIVE_DIRECT_QUERY",
                    "description": "created by direct CLI test",
                    "formula": "let Source = #table({\"Code\",\"Amount\"}, {{\"A\", 1}, {\"B\", 2}}) in Source",
                }
            )

            set_proc = run_skill_cli("query", "set", "--workbook-path", str(workbook), "--spec-json", spec, timeout=300)
            self.assertEqual(set_proc.returncode, 0, set_proc.stdout + set_proc.stderr)
            self.assertEqual(json.loads(set_proc.stdout)["query"]["name"], "LIVE_DIRECT_QUERY")

            get_proc = run_skill_cli("query", "get", "--workbook-path", str(workbook), "--query-name", "LIVE_DIRECT_QUERY", timeout=300)
            self.assertEqual(get_proc.returncode, 0, get_proc.stdout + get_proc.stderr)
            self.assertIn("Code", json.loads(get_proc.stdout)["query"]["formula"])

            connection_list_proc = run_skill_cli("connection", "list", "--workbook-path", str(workbook), timeout=300)
            self.assertEqual(connection_list_proc.returncode, 0, connection_list_proc.stdout + connection_list_proc.stderr)
            self.assertIsInstance(json.loads(connection_list_proc.stdout)["connections"], list)

            delete_proc = run_skill_cli("query", "delete", "--workbook-path", str(workbook), "--query-name", "LIVE_DIRECT_QUERY", timeout=300)
            self.assertEqual(delete_proc.returncode, 0, delete_proc.stdout + delete_proc.stderr)
            self.assertTrue(json.loads(delete_proc.stdout)["deleted"])

    @unittest.skipUnless(os.environ.get("EXCEL_SYNC_LIVE") == "1", "set EXCEL_SYNC_LIVE=1 to run live Excel COM tests")
    def test_live_direct_chart_and_pivot_list_commands_return_arrays(self) -> None:
        if not FIXTURE_WORKBOOK.exists():
            self.skipTest("fixture workbook is unavailable")

        chart_proc = run_skill_cli("chart", "list", "--workbook-path", str(FIXTURE_WORKBOOK), timeout=300)
        self.assertEqual(chart_proc.returncode, 0, chart_proc.stdout + chart_proc.stderr)
        self.assertIsInstance(json.loads(chart_proc.stdout)["charts"], list)

        pivot_proc = run_skill_cli("pivot", "list", "--workbook-path", str(FIXTURE_WORKBOOK), timeout=300)
        self.assertEqual(pivot_proc.returncode, 0, pivot_proc.stdout + pivot_proc.stderr)
        self.assertIsInstance(json.loads(pivot_proc.stdout)["pivots"], list)

    @unittest.skipUnless(os.environ.get("EXCEL_SYNC_LIVE") == "1", "set EXCEL_SYNC_LIVE=1 to run live Excel COM tests")
    def test_live_generic_pull_supports_xls_and_xlsb(self) -> None:
        if not FIXTURE_WORKBOOK.exists():
            self.skipTest("fixture workbook is unavailable")
        with tempfile.TemporaryDirectory(prefix="excel-foundry-live-legacy-") as tmpdir:
            tmp = Path(tmpdir)
            source = tmp / "source.xlsm"
            shutil.copy2(FIXTURE_WORKBOOK, source)
            legacy_xls = tmp / "legacy.xls"
            binary_xlsb = tmp / "legacy.xlsb"
            save_workbook_as_format(source, legacy_xls, 56)
            save_workbook_as_format(source, binary_xlsb, 50)

            for workbook in [legacy_xls, binary_xlsb]:
                output_root = tmp / workbook.stem
                proc = subprocess.run(
                    [
                        "python",
                        str(ROOT / "scripts" / "excel_workbook_sync.py"),
                        "pull",
                        "--workbook",
                        str(workbook),
                        "--output-root",
                        str(output_root),
                        "--engine",
                        "com",
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                    timeout=300,
                )
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                payload = json.loads(proc.stdout)
                self.assertEqual(payload["engine"], "com")
                self.assertTrue((output_root / "normalized.json").exists())
                self.assertFalse((output_root / "ooxml-parts").exists())

    @unittest.skipUnless(os.environ.get("EXCEL_SYNC_LIVE") == "1", "set EXCEL_SYNC_LIVE=1 to run live Excel COM tests")
    def test_live_compare_reports_package_unavailable_for_xls_and_xlsb(self) -> None:
        if not FIXTURE_WORKBOOK.exists():
            self.skipTest("fixture workbook is unavailable")
        with tempfile.TemporaryDirectory(prefix="excel-foundry-live-legacy-compare-") as tmpdir:
            tmp = Path(tmpdir)
            source = tmp / "source.xlsm"
            shutil.copy2(FIXTURE_WORKBOOK, source)
            legacy_xls = tmp / "legacy.xls"
            binary_xlsb = tmp / "legacy.xlsb"
            save_workbook_as_format(source, legacy_xls, 56)
            save_workbook_as_format(source, binary_xlsb, 50)

            for workbook in [legacy_xls, binary_xlsb]:
                output_root = tmp / f"{workbook.stem}-compare"
                proc = subprocess.run(
                    [
                        "python",
                        str(ROOT / "scripts" / "excel_workbook_sync.py"),
                        "compare",
                        "--workbook",
                        str(workbook),
                        "--output-root",
                        str(output_root),
                        "--engine",
                        "com",
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                    timeout=300,
                )
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                payload = json.loads(proc.stdout)
                self.assertFalse(payload["comparisonAvailable"])
                self.assertEqual(payload["comparisonStatus"], "package_unavailable")
                self.assertIsNone(payload["match"])


if __name__ == "__main__":
    unittest.main()
