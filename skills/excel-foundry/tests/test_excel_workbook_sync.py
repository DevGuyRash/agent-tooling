from __future__ import annotations

import json
import os
import argparse
import shutil
import subprocess
import tempfile
import unittest
import zipfile
import base64
import importlib.util
import re
from io import BytesIO
from pathlib import Path
from textwrap import dedent


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
POSIX = ROOT / "scripts" / "excel-foundry"
CMD = ROOT / "scripts" / "excel-foundry.cmd"
PS1 = ROOT / "scripts" / "excel-foundry.ps1"
COMMON = ROOT / "scripts" / "ExcelSync.Common.ps1"
POWERQUERY = ROOT / "scripts" / "sync-excel-powerquery.ps1"
OPENAI_YAML = ROOT / "agents" / "openai.yaml"
CAPABILITY_MATRIX = ROOT / "references" / "excel-capability-matrix.json"
RUNTIME_COMPATIBILITY = ROOT / "references" / "runtime-compatibility.md"
EXTERNAL_SMOKE_TEST = ROOT / "tests" / "test_excel_workbook_external_smoke.py"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "generic_workbook_fixture"
FIXTURE_MANIFEST = ROOT / "tests" / "fixtures" / "generic_workbook_fixture" / "excel-sync.manifest.json"
FIXTURE_WORKBOOK = FIXTURE_DIR / "workflow_fixture.xlsm"
HAS_PWSH = shutil.which("pwsh") is not None
HAS_CMD = shutil.which("cmd") is not None
LIVE_DESKTOP = os.environ.get("EXCEL_FOUNDRY_LIVE_DESKTOP") == "1"
LIVE_MUTATION = os.environ.get("EXCEL_FOUNDRY_LIVE_MUTATION") == "1"
LIVE_DESKTOP_MUTATION = LIVE_DESKTOP and LIVE_MUTATION


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


def load_package_module(module_name: str = "excel_workbook_package_for_cloud_tests"):
    package_spec = importlib.util.spec_from_file_location(
        module_name,
        ROOT / "scripts" / "excel_workbook_package.py",
    )
    package_module = importlib.util.module_from_spec(package_spec)
    assert package_spec.loader is not None
    package_spec.loader.exec_module(package_module)
    return package_module


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


def build_minimal_ooxml_workbook(workbook_path: Path, *, include_chart: bool = False) -> None:
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

    sheet_drawing = ""
    drawing_rel = ""
    drawing_part = {}
    chart_part = {}
    chart_content_types = ""
    if include_chart:
        sheet_drawing = '\n              <drawing r:id="rId4"/>'
        drawing_rel = '\n              <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/>'
        chart_content_types = (
            '              <Override PartName="/xl/drawings/drawing1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>\n'
            '              <Override PartName="/xl/charts/chart1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml"/>\n'
        )
        drawing_part = {
            "xl/drawings/drawing1.xml": dedent(
                """\
                <?xml version="1.0" encoding="UTF-8"?>
                <xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
                  <xdr:twoCellAnchor>
                    <xdr:from><xdr:col>4</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>1</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>
                    <xdr:to><xdr:col>10</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>15</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to>
                    <xdr:graphicFrame macro="">
                      <xdr:nvGraphicFramePr>
                        <xdr:cNvPr id="2" name="Chart 1"/>
                        <xdr:cNvGraphicFramePr/>
                      </xdr:nvGraphicFramePr>
                      <xdr:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></xdr:xfrm>
                      <a:graphic>
                        <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart">
                          <c:chart xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="rId1"/>
                        </a:graphicData>
                      </a:graphic>
                    </xdr:graphicFrame>
                    <xdr:clientData/>
                  </xdr:twoCellAnchor>
                </xdr:wsDr>
                """
            ),
            "xl/drawings/_rels/drawing1.xml.rels": dedent(
                """\
                <?xml version="1.0" encoding="UTF-8"?>
                <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
                  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart" Target="../charts/chart1.xml"/>
                </Relationships>
                """
            ),
        }
        chart_part = {
            "xl/charts/chart1.xml": dedent(
                """\
                <?xml version="1.0" encoding="UTF-8"?>
                <c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
                  <c:chart>
                    <c:title>
                      <c:tx>
                        <c:rich>
                          <a:bodyPr/>
                          <a:lstStyle/>
                          <a:p><a:r><a:t>Sales</a:t></a:r></a:p>
                        </c:rich>
                      </c:tx>
                      <c:overlay val="0"/>
                    </c:title>
                    <c:plotArea>
                      <c:layout/>
                      <c:barChart>
                        <c:barDir val="col"/>
                        <c:grouping val="clustered"/>
                        <c:ser>
                          <c:idx val="0"/>
                          <c:order val="0"/>
                          <c:tx><c:strRef><c:f>Sheet1!$B$1</c:f></c:strRef></c:tx>
                          <c:cat><c:strRef><c:f>Sheet1!$A$2</c:f></c:strRef></c:cat>
                          <c:val><c:numRef><c:f>Sheet1!$B$2</c:f></c:numRef></c:val>
                        </c:ser>
                      </c:barChart>
                    </c:plotArea>
                  </c:chart>
                </c:chartSpace>
                """
            )
        }

    workbook_files = {
        "[Content_Types].xml": dedent(
            f"""\
            <?xml version="1.0" encoding="UTF-8"?>
            <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
              <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
              <Default Extension="xml" ContentType="application/xml"/>
              <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
              <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
              <Override PartName="/xl/tables/table1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.table+xml"/>
              <Override PartName="/xl/queryTables/queryTable1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.queryTable+xml"/>
              <Override PartName="/xl/connections.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.connections+xml"/>
              <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
              <Override PartName="/xl/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
              <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
              <Override PartName="/xl/comments1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.comments+xml"/>
              <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
              <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
              <Override PartName="/docProps/custom.xml" ContentType="application/vnd.openxmlformats-officedocument.custom-properties+xml"/>
              <Override PartName="/customXml/item1.xml" ContentType="application/xml"/>
              <Override PartName="/customXml/itemProps1.xml" ContentType="application/vnd.openxmlformats-officedocument.customXmlProperties+xml"/>
{chart_content_types.rstrip()}
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
              <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
              <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>
            </Relationships>
            """
        ),
        "xl/worksheets/sheet1.xml": dedent(
            f"""\
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
{sheet_drawing}
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
            f"""\
            <?xml version="1.0" encoding="UTF-8"?>
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/table" Target="../tables/table1.xml"/>
              <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.com/report" TargetMode="External"/>
              <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="../comments1.xml"/>
{drawing_rel.rstrip()}
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
        "xl/styles.xml": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <fonts count="1"><font><sz val="11"/><color theme="1"/><name val="Calibri"/></font></fonts>
              <fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
              <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
              <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
              <cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
              <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
            </styleSheet>
            """
        ),
        "xl/theme/theme1.xml": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Office">
              <a:themeElements>
                <a:clrScheme name="Office">
                  <a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>
                  <a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>
                  <a:accent1><a:srgbClr val="4472C4"/></a:accent1>
                </a:clrScheme>
                <a:fontScheme name="Office"><a:majorFont/><a:minorFont/></a:fontScheme>
                <a:fmtScheme name="Office"/>
              </a:themeElements>
            </a:theme>
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
    workbook_files.update(drawing_part)
    workbook_files.update(chart_part)

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
        self.assertTrue(RUNTIME_COMPATIBILITY.exists())
        self.assertTrue(CAPABILITY_MATRIX.exists())

    def test_skill_frontmatter_stays_skill_creator_valid(self) -> None:
        content = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(content.startswith("---\n"))
        frontmatter = content.split("---", 2)[1]
        keys = [
            line.split(":", 1)[0]
            for line in frontmatter.splitlines()
            if line and not line.startswith(" ") and ":" in line
        ]
        self.assertEqual(keys, ["name", "description"])
        self.assertIn("name: excel-foundry", frontmatter)
        self.assertNotIn("compatibility:", frontmatter)
        self.assertNotIn("metadata:", frontmatter)

        body = content.split("---", 2)[2]
        self.assertIn("references/runtime-compatibility.md", body)

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

    def test_capability_matrix_maps_surfaces_to_existing_tests_and_honest_routes(self) -> None:
        matrix = json.loads(CAPABILITY_MATRIX.read_text(encoding="utf-8"))
        package_spec = importlib.util.spec_from_file_location(
            "excel_workbook_package_for_matrix_evidence",
            ROOT / "scripts" / "excel_workbook_package.py",
        )
        package_module = importlib.util.module_from_spec(package_spec)
        assert package_spec.loader is not None
        package_spec.loader.exec_module(package_module)
        ledger = package_module.CAPABILITY_LEDGER

        test_sources = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "tests").glob("test_*.py"))
        discovered_tests = set(re.findall(r"def (test_[A-Za-z0-9_]+)\(", test_sources))

        covered_surfaces: set[str] = set()
        for surface in matrix["surfaces"]:
            surface_id = surface["id"]
            self.assertIn(surface_id, ledger, surface_id)
            covered_surfaces.add(surface_id)
            self.assertEqual(surface["readLane"], ledger[surface_id]["read"], surface_id)
            self.assertEqual(surface["writeLane"], ledger[surface_id]["write"], surface_id)
            self.assertEqual(surface["route"], ledger[surface_id]["route"], surface_id)
            self.assertGreater(surface.get("evidenceSelectors", []), [], surface_id)
            for selector in surface["evidenceSelectors"]:
                self.assertIn(selector, discovered_tests, f"{surface_id} references missing test {selector}")

        self.assertEqual(set(ledger), covered_surfaces)

    def test_capability_matrix_declares_all_surfaces_with_routes_and_evidence(self) -> None:
        matrix = json.loads(CAPABILITY_MATRIX.read_text(encoding="utf-8"))
        self.assertEqual(matrix["version"], 1)
        self.assertEqual(matrix["contract"], "Hybrid Parity")
        self.assertEqual(matrix["secretPolicy"], "Never Store")
        self.assertIn("list", matrix["operationVocabulary"])
        self.assertIn("plan", matrix["operationVocabulary"])
        self.assertIn("preserve-only", matrix["supportLevels"])
        compatibility_fields = matrix["environmentCompatibilityFields"]
        self.assertEqual(compatibility_fields, ["package", "desktop", "graph", "officeScript", "tomFabric"])
        self.assertIn("remain authoritative even when the overall supportLevel is host-limited", matrix["environmentCompatibilityRule"])
        allowed_compatibility = set(matrix["environmentCompatibilityLevels"])

        package_spec = importlib.util.spec_from_file_location(
            "excel_workbook_package_for_capability_matrix",
            ROOT / "scripts" / "excel_workbook_package.py",
        )
        package_module = importlib.util.module_from_spec(package_spec)
        assert package_spec.loader is not None
        package_spec.loader.exec_module(package_module)
        ledger = package_module.CAPABILITY_LEDGER

        test_sources = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "tests").glob("test_*.py"))
        discovered_tests = set(re.findall(r"def (test_[A-Za-z0-9_]+)\(", test_sources))
        allowed_support = set(matrix["supportLevels"])
        allowed_routes = {
            "package-write",
            "desktop-write",
            "partial-package-write",
            "automation-write",
            "graph-write",
            "tom-fabric-write",
            "preserve-only",
        }
        allowed_closure_reasons = set(matrix["closureReasons"])
        allowed_lanes = {"package", "desktop", "desktop-preferred", "automation", "graph", "tom-fabric", "preserve-only"}
        seen_ids: set[str] = set()

        for surface in matrix["surfaces"]:
            surface_id = surface["id"]
            self.assertNotIn(surface_id, seen_ids)
            seen_ids.add(surface_id)
            self.assertIn(surface_id, ledger)
            self.assertIn(surface["supportLevel"], allowed_support)
            for field in compatibility_fields:
                self.assertIn(field, surface, surface_id)
                self.assertIn(surface[field], allowed_compatibility, f"{surface_id}.{field}")
            if surface["supportLevel"] == "host-limited":
                self.assertTrue(
                    any(surface[field] in {"supported", "partial", "preserve-only", "planned"} for field in compatibility_fields),
                    surface_id,
                )
            self.assertIn(surface["readLane"], allowed_lanes)
            self.assertIn(surface["writeLane"], allowed_lanes)
            self.assertIn(surface["route"], allowed_routes)
            self.assertIn(surface["closureReason"], allowed_closure_reasons, surface_id)
            if surface["supportLevel"] != "supported":
                self.assertIn(
                    surface["closureReason"],
                    {
                        "public-api-supported",
                        "host-api-required",
                        "preserve-only-opaque",
                        "tenant-policy-required",
                        "no-public-mutation-api",
                    },
                    surface_id,
                )
            self.assertGreater(surface.get("documentationAnchors", []), [], surface_id)
            for anchor in surface["documentationAnchors"]:
                self.assertIn("document", anchor, surface_id)
                self.assertIn("route", anchor, surface_id)
                self.assertGreater(anchor.get("proves", []), [], surface_id)
                self.assertTrue(
                    {"mutation", "readback", "inventory", "preservation", "limitation"} & set(anchor["proves"]),
                    surface_id,
                )
            self.assertGreater(surface["operations"], [], surface_id)
            self.assertTrue({"inspect", "plan"} & set(surface["operations"]), surface_id)
            self.assertGreater(surface["hostRequirements"], [], surface_id)
            secret_policy = surface["secretPolicy"].lower()
            self.assertTrue(
                any(
                    token in secret_policy
                    for token in [
                        "serialized",
                        "stored",
                        "runtime-only",
                        "remain in",
                        "stays in",
                        "preserved in",
                        "outside committed",
                    ]
                ),
                surface_id,
            )
            self.assertGreater(surface["evidenceSelectors"], [], surface_id)
            for selector in surface["evidenceSelectors"]:
                self.assertIn(selector, discovered_tests, f"{surface_id} references missing test {selector}")

            if surface["supportLevel"] == "supported":
                self.assertNotIn(surface["writeLane"], {"graph", "tom-fabric", "preserve-only"}, surface_id)
            if surface["writeLane"] in {"graph", "tom-fabric"}:
                self.assertIn(surface["supportLevel"], {"planned", "host-limited", "partial"}, surface_id)
            if surface["supportLevel"] != "supported":
                planned_fields = [field for field in compatibility_fields if surface[field] == "planned"]
                self.assertEqual(planned_fields, [], f"{surface_id} has unfinished backend fields")

        self.assertEqual(set(ledger), seen_ids)

    def test_capability_matrix_declares_explicit_advanced_excel_surfaces(self) -> None:
        matrix = json.loads(CAPABILITY_MATRIX.read_text(encoding="utf-8"))
        surface_ids = {surface["id"] for surface in matrix["surfaces"]}
        advanced_surfaces = {
            "cube-functions",
            "sparklines",
            "calc-engine",
            "lambda-names",
            "xml-maps",
            "custom-xml",
            "ole-objects",
            "external-data-ranges",
            "workbook-views",
            "signatures",
            "encryption",
            "sensitivity-irm",
            "solver",
            "forecast-sheets",
            "data-tables",
            "office-script-live",
            "addin-runtime",
        }
        self.assertLessEqual(advanced_surfaces, surface_ids)

        surfaces = {surface["id"]: surface for surface in matrix["surfaces"]}
        for surface_id in advanced_surfaces:
            with self.subTest(surface=surface_id):
                surface = surfaces[surface_id]
                self.assertGreater(surface["operations"], [])
                self.assertIn(surface["supportLevel"], {"partial", "host-limited", "preserve-only"})
                self.assertNotEqual(surface["supportLevel"], "supported")
                self.assertGreater(surface["hostRequirements"], [])
                self.assertGreater(surface["evidenceSelectors"], [])

    def test_development_governance_rules_are_enforced_by_tests_and_matrix(self) -> None:
        matrix = json.loads(CAPABILITY_MATRIX.read_text(encoding="utf-8"))
        development = (ROOT / "DEVELOPMENT.md").read_text(encoding="utf-8")
        test_files = sorted((ROOT / "tests").glob("test_*.py"))
        committed_test_sources = {path.name: path.read_text(encoding="utf-8") for path in test_files}
        committed_test_text = "\n".join(committed_test_sources.values())

        package_spec = importlib.util.spec_from_file_location(
            "excel_workbook_package_for_development_governance",
            ROOT / "scripts" / "excel_workbook_package.py",
        )
        package_module = importlib.util.module_from_spec(package_spec)
        assert package_spec.loader is not None
        package_spec.loader.exec_module(package_module)
        ledger = package_module.CAPABILITY_LEDGER

        self.assertIn("## Capability Source Of Truth", development)
        self.assertIn("## Skill Metadata", development)
        self.assertIn("You SHALL keep `SKILL.md` frontmatter limited to `name` and `description`.", development)
        self.assertIn("references/runtime-compatibility.md", development)
        self.assertIn("`references/excel-capability-matrix.json` is the single source of truth", development)
        self.assertIn("You SHALL NOT create a second capability matrix", development)
        self.assertIn("WHEN planning a new Excel Foundry feature THEN you SHALL start", development)
        self.assertIn("WHEN marking a surface `supported` THEN you SHALL add direct", development)
        self.assertIn("test_capability_matrix_maps_surfaces_to_existing_tests_and_honest_routes", development)

        discovered_tests = set(re.findall(r"def (test_[A-Za-z0-9_]+)\(", committed_test_text))
        self.assertIn("test_development_governance_rules_are_enforced_by_tests_and_matrix", discovered_tests)

        covered_surfaces: set[str] = set()
        private_patterns = [
            r"\.local[\\/]files[\\/]excel-foundry",
            r"EXCEL_SYNC_EXTERNAL_ROOTS\s*=\s*\.local",
            r"C:[\\/]Users[\\/]",
            re.escape(str(Path.home())),
        ]
        local_external_corpus = ".local" + "/files/excel-foundry"
        for pattern in private_patterns:
            self.assertIsNone(re.search(pattern, committed_test_text, flags=re.IGNORECASE), pattern)
            self.assertIsNone(re.search(pattern, json.dumps(matrix), flags=re.IGNORECASE), pattern)

        for surface in matrix["surfaces"]:
            surface_id = surface["id"]
            self.assertGreater(surface.get("evidenceSelectors", []), [], surface_id)
            for selector in surface["evidenceSelectors"]:
                self.assertIn(selector, discovered_tests, f"{surface_id} references missing test {selector}")
            self.assertIn(surface_id, ledger, surface_id)
            covered_surfaces.add(surface_id)
            write_lane = ledger[surface_id]["write"]
            if write_lane == "desktop":
                self.assertIn("desktop", surface["route"], surface_id)
            if write_lane == "desktop-preferred":
                self.assertIn("partial", surface["route"], surface_id)
            if write_lane == "preserve-only":
                self.assertIn("preserve", surface["route"], surface_id)
            if write_lane == "graph":
                self.assertIn("graph", surface["route"], surface_id)
            if write_lane == "tom-fabric":
                self.assertIn("tom-fabric", surface["route"], surface_id)
            if write_lane == "automation":
                self.assertTrue(
                    any(token in surface["route"] for token in ["automation", "desktop"]),
                    surface_id,
                )

        self.assertEqual(set(ledger), covered_surfaces)

        external_source = committed_test_sources[EXTERNAL_SMOKE_TEST.name]
        self.assertIn('os.environ.get("EXCEL_SYNC_EXTERNAL_ROOTS", "")', external_source)
        self.assertIn("raise unittest.SkipTest", external_source)
        self.assertIn("copy_external_roots_to_temp(cls.original_roots", external_source)
        self.assertIn('tempfile.TemporaryDirectory(prefix="excel-sync-external-corpus-"', external_source)
        self.assertIn("shutil.copy2(root, target)", external_source)
        self.assertIn("shutil.copytree(root, target)", external_source)
        self.assertNotIn(local_external_corpus, external_source)

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

    def test_manifest_resolution_accepts_vba_only_manifest_without_structure(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-vba-only-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "vba-only.xlsm"
            workbook.write_bytes(b"")
            module = tmp / "modLiveProbe.bas"
            module.write_text('Attribute VB_Name = "modLiveProbe"\n', encoding="utf-8")
            manifest = tmp / "excel-sync.manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "workbookPath": workbook.name,
                        "vbaComponents": [
                            {"name": "modLiveProbe", "path": module.name},
                        ],
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
                    "vbaCount=@($resolved.VbaComponents).Count;"
                    "firstVbaPath=$resolved.VbaComponents[0].Path;"
                    "tablesPath=$resolved.Structure.TablesPath;"
                    "queriesPath=$resolved.PowerQuery.QueriesPath"
                    "} | ConvertTo-Json -Compress -Depth 20"
                )
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(Path(payload["workbookPath"]), workbook.resolve())
            self.assertEqual(payload["vbaCount"], 1)
            self.assertEqual(Path(payload["firstVbaPath"]), module.resolve())
            self.assertIsNone(payload["tablesPath"])
            self.assertIsNone(payload["queriesPath"])

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
                    sheet = 'DATA_RECORDS'
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
                    sheet = 'DATA_RECORDS'
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
                    sheet = 'DATA_RECORDS'
                    address = '$C$5:$C$9'
                    type = 'expression'
                    formula = '=TRUE'
                    priority = 8
                    format = [pscustomobject]@{{ interiorColor = '#00FF00' }}
                }}
                $candidates = @(
                    [pscustomobject]@{{ id='A'; sheet='DATA_RECORDS'; address='$C$5:$C$9'; type='expression'; formula='=TRUE'; priority=3; format=[pscustomobject]@{{ interiorColor = '#00FF00' }} }},
                    [pscustomobject]@{{ id='B'; sheet='DATA_RECORDS'; address='$C$5:$C$9'; type='expression'; formula='=TRUE'; priority=7; format=[pscustomobject]@{{ interiorColor = '#00FF00' }} }}
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
                    sheet = 'DATA_RECORDS'
                    address = '$C$5:$C$9'
                    type = 'expression'
                    formula = '=TRUE'
                    priority = 8
                    format = [pscustomobject]@{{ interiorColor = '#00FF00' }}
                }}
                $candidates = @(
                    [pscustomobject]@{{ id='A'; sheet='DATA_RECORDS'; address='$C$5:$C$9'; type='expression'; formula='=TRUE'; priority=7; format=[pscustomobject]@{{ interiorColor = '#00FF00' }} }},
                    [pscustomobject]@{{ id='B'; sheet='DATA_RECORDS'; address='$C$5:$C$9'; type='expression'; formula='=TRUE'; priority=9; format=[pscustomobject]@{{ interiorColor = '#00FF00' }} }}
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
        for resource in ["connection", "chart", "shape", "picture", "control", "pivot"]:
            self.assertIn(resource, proc.stdout)
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
            self.assertEqual(payload["charts"], [])
            self.assertEqual(len(payload["pq"]), 1)
            self.assertEqual(payload["pq"][0]["name"], "Query1")
            self.assertEqual(payload["pq"][0]["connectionName"], "Query - Query1")
            self.assertEqual(payload["pq"][0]["loads"][0]["table"], "Table1")
            self.assertEqual(len(payload["connections"]), 1)

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_package_backend_query_reads_chart_metadata_from_ooxml_workbook(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-package-chart-") as tmpdir:
            workbook = Path(tmpdir) / "package-chart-workbook.xlsx"
            build_minimal_ooxml_workbook(workbook, include_chart=True)
            proc = run_pwsh_file(
                "query",
                "--workbook-path",
                str(workbook),
                "--surface",
                "charts",
                "--backend",
                "package",
                timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["backend"], "package")
            self.assertEqual(len(payload["charts"]), 1)
            chart = payload["charts"][0]
            self.assertEqual(chart["name"], "Chart 1")
            self.assertEqual(chart["kind"], "embedded")
            self.assertEqual(chart["sheet"], "Sheet1")
            self.assertEqual(chart["address"], "E2:K16")
            self.assertEqual(chart["chartType"], "barChart")
            self.assertTrue(chart["hasTitle"])
            self.assertEqual(chart["title"], "Sales")
            self.assertEqual(chart["series"][0]["name"], "Sheet1!$B$1")
            self.assertEqual(chart["series"][0]["formula"], "=SERIES(Sheet1!$B$1,Sheet1!$A$2,Sheet1!$B$2,0)")
            self.assertFalse(any(item["surface"] == "charts" for item in payload["unsupported"]))

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
    def test_sheet_delete_requires_destructive_and_removes_package_sheet(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-sheet-delete-") as tmpdir:
            workbook = Path(tmpdir) / "package-workbook.xlsx"
            build_minimal_ooxml_workbook(workbook)

            create_proc = run_pwsh_file("sheet", "create", "--workbook-path", str(workbook), "--sheet", "ToDelete", timeout=60)
            self.assertEqual(create_proc.returncode, 0, create_proc.stdout + create_proc.stderr)

            guard_proc = run_pwsh_file("sheet", "delete", "--workbook-path", str(workbook), "--sheet", "ToDelete", timeout=60)
            self.assertEqual(guard_proc.returncode, 0, guard_proc.stdout + guard_proc.stderr)
            self.assertEqual(json.loads(guard_proc.stdout)["status"], "blocked")

            delete_proc = run_pwsh_file("sheet", "delete", "--workbook-path", str(workbook), "--sheet", "ToDelete", "--destructive", timeout=60)
            self.assertEqual(delete_proc.returncode, 0, delete_proc.stdout + delete_proc.stderr)
            self.assertTrue(json.loads(delete_proc.stdout)["deleted"])

            list_proc = run_pwsh_file("sheet", "list", "--workbook-path", str(workbook), timeout=60)
            self.assertEqual(list_proc.returncode, 0, list_proc.stdout + list_proc.stderr)
            self.assertNotIn("ToDelete", {item["name"] for item in json.loads(list_proc.stdout)["sheets"]})

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

            plan_proc = run_pwsh_file("plan", "--manifest-path", str(manifest), "--workbook-path", str(workbook), "--surface", "pq", timeout=60)
            self.assertEqual(plan_proc.returncode, 0, plan_proc.stdout + plan_proc.stderr)
            plan_payload = json.loads(plan_proc.stdout)
            pq_plan = plan_payload["surfaces"][0]
            self.assertEqual(pq_plan["surface"], "pq")
            self.assertEqual(pq_plan["route"], "desktop-write")
            self.assertEqual(pq_plan["engineRoute"]["requiresBackend"], "desktop")
            self.assertFalse(pq_plan["canWrite"])

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

            deep_proc = run_pwsh_file("workbook", "capabilities", "--workbook-path", str(workbook), "--deep", timeout=60)
            self.assertEqual(deep_proc.returncode, 0, deep_proc.stdout + deep_proc.stderr)
            ledger = json.loads(deep_proc.stdout)["capabilityLedger"]
            self.assertGreaterEqual(ledger["counts"]["surfaces"], 40)
            self.assertEqual(ledger["surfaces"]["tables"]["route"], "package-write")
            self.assertEqual(ledger["surfaces"]["charts"]["route"], "partial-package-write")
            self.assertTrue(ledger["surfaces"]["charts"]["canWriteHere"])
            self.assertEqual(ledger["surfaces"]["pivots"]["route"], "desktop-write")
            self.assertEqual(ledger["surfaces"]["artifact-workbook"]["route"], "automation-write")
            self.assertEqual(ledger["surfaces"]["legacy-bi"]["route"], "preserve-only")
            self.assertEqual(ledger["surfaces"]["sheets"]["risk"], "destructive-delete-guarded")

            documentation_proc = run_pwsh_file(
                "workbook",
                "capabilities",
                "--workbook-path",
                str(workbook),
                "--deep",
                "--documentation",
                timeout=60,
            )
            self.assertEqual(documentation_proc.returncode, 0, documentation_proc.stdout + documentation_proc.stderr)
            documentation_payload = json.loads(documentation_proc.stdout)
            documentation_ledger = documentation_payload["capabilityLedger"]
            self.assertIn("closureReasons", documentation_payload)
            self.assertEqual(
                documentation_ledger["surfaces"]["tables"]["documentationAnchors"][0]["route"],
                "package-write",
            )
            self.assertEqual(
                documentation_ledger["surfaces"]["legacy-bi"]["closureReason"],
                "preserve-only-opaque",
            )

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
    def test_package_backend_sync_push_apply_updates_existing_chart_references(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-sync-charts-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "sync-charts.xlsx"
            build_minimal_ooxml_workbook(workbook, include_chart=True)
            output_dir = tmp / "bundle"
            bootstrap_proc = run_pwsh_file(
                "bootstrap",
                "--workbook-path",
                str(workbook),
                "--output-dir",
                str(output_dir),
                "--surface",
                "charts",
                "--backend",
                "package",
                timeout=60,
            )
            self.assertEqual(bootstrap_proc.returncode, 0, bootstrap_proc.stdout + bootstrap_proc.stderr)
            manifest = output_dir / "excel-sync.manifest.json"
            charts_path = output_dir / "workbook_structure" / "charts.json"
            charts_payload = json.loads(charts_path.read_text(encoding="utf-8"))
            chart = charts_payload["charts"][0]
            self.assertEqual(chart["name"], "Chart 1")
            chart["title"] = "Updated Sales"
            chart["series"][0]["nameFormula"] = "Sheet1!$C$1"
            chart["series"][0]["categoriesFormula"] = "Sheet1!$A$2"
            chart["series"][0]["valuesFormula"] = "Sheet1!$C$2"
            charts_path.write_text(json.dumps(charts_payload, indent=2) + "\n", encoding="utf-8")

            plan_proc = run_pwsh_file("plan", "--manifest-path", str(manifest), "--surface", "charts", "--mode", "push", timeout=60)
            self.assertEqual(plan_proc.returncode, 0, plan_proc.stdout + plan_proc.stderr)
            chart_plan = json.loads(plan_proc.stdout)["surfaces"][0]
            self.assertEqual(chart_plan["route"], "partial-package-write")
            self.assertTrue(chart_plan["canWrite"])

            sync_proc = run_pwsh_file(
                "sync",
                "--manifest-path",
                str(manifest),
                "--surface",
                "charts",
                "--mode",
                "push",
                "--apply",
                timeout=60,
            )
            self.assertEqual(sync_proc.returncode, 0, sync_proc.stdout + sync_proc.stderr)
            chart_result = json.loads(sync_proc.stdout)["surfaces"][0]
            self.assertEqual(chart_result["status"], "applied")
            self.assertIn("Applied chart title and series reference updates", " ".join(chart_result["messages"]))

            query_proc = run_pwsh_file(
                "query",
                "--workbook-path",
                str(workbook),
                "--surface",
                "charts",
                "--backend",
                "package",
                timeout=60,
            )
            self.assertEqual(query_proc.returncode, 0, query_proc.stdout + query_proc.stderr)
            updated_chart = json.loads(query_proc.stdout)["charts"][0]
            self.assertEqual(updated_chart["title"], "Updated Sales")
            self.assertEqual(updated_chart["series"][0]["nameFormula"], "Sheet1!$C$1")
            self.assertEqual(updated_chart["series"][0]["categoriesFormula"], "Sheet1!$A$2")
            self.assertEqual(updated_chart["series"][0]["valuesFormula"], "Sheet1!$C$2")

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_package_backend_sync_push_apply_updates_styles_and_themes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-sync-styles-themes-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "sync-styles-themes.xlsx"
            build_minimal_ooxml_workbook(workbook)
            output_dir = tmp / "bundle"
            bootstrap_proc = run_pwsh_file(
                "bootstrap",
                "--workbook-path",
                str(workbook),
                "--output-dir",
                str(output_dir),
                "--surface",
                "styles,themes",
                "--backend",
                "package",
                timeout=60,
            )
            self.assertEqual(bootstrap_proc.returncode, 0, bootstrap_proc.stdout + bootstrap_proc.stderr)
            manifest = output_dir / "excel-sync.manifest.json"
            styles_path = output_dir / "workbook_structure" / "styles.json"
            themes_path = output_dir / "workbook_structure" / "themes.json"

            styles_payload = json.loads(styles_path.read_text(encoding="utf-8"))
            self.assertEqual(styles_payload["parts"][0]["path"], "xl/styles.xml")
            styles_payload["parts"][0]["xml"] = styles_payload["parts"][0]["xml"].replace('name val="Calibri"', 'name val="Aptos"')
            styles_path.write_text(json.dumps(styles_payload, indent=2) + "\n", encoding="utf-8")

            themes_payload = json.loads(themes_path.read_text(encoding="utf-8"))
            self.assertEqual(themes_payload["parts"][0]["path"], "xl/theme/theme1.xml")
            themes_payload["parts"][0]["xml"] = themes_payload["parts"][0]["xml"].replace('name="Office"', 'name="Foundry Office"', 1).replace('val="4472C4"', 'val="5B9BD5"')
            themes_path.write_text(json.dumps(themes_payload, indent=2) + "\n", encoding="utf-8")

            plan_proc = run_pwsh_file("plan", "--manifest-path", str(manifest), "--surface", "styles,themes", "--mode", "push", timeout=60)
            self.assertEqual(plan_proc.returncode, 0, plan_proc.stdout + plan_proc.stderr)
            plan_payload = json.loads(plan_proc.stdout)
            self.assertEqual([item["surface"] for item in plan_payload["surfaces"]], ["styles", "themes"])
            self.assertTrue(all(item["canWrite"] for item in plan_payload["surfaces"]))

            sync_proc = run_pwsh_file(
                "sync",
                "--manifest-path",
                str(manifest),
                "--surface",
                "styles,themes",
                "--mode",
                "push",
                "--apply",
                timeout=60,
            )
            self.assertEqual(sync_proc.returncode, 0, sync_proc.stdout + sync_proc.stderr)
            sync_payload = json.loads(sync_proc.stdout)
            self.assertEqual([item["status"] for item in sync_payload["surfaces"]], ["applied", "applied"])
            self.assertIn("Applied 1 styles package part replacement", " ".join(sync_payload["surfaces"][0]["messages"]))
            self.assertIn("Applied 1 themes package part replacement", " ".join(sync_payload["surfaces"][1]["messages"]))

            query_proc = run_pwsh_file(
                "query",
                "--workbook-path",
                str(workbook),
                "--surface",
                "styles,themes",
                "--backend",
                "package",
                timeout=60,
            )
            self.assertEqual(query_proc.returncode, 0, query_proc.stdout + query_proc.stderr)
            query_payload = json.loads(query_proc.stdout)
            self.assertIn('name val="Aptos"', query_payload["styles"]["parts"][0]["xml"])
            self.assertEqual(query_payload["themes"]["parts"][0]["name"], "Foundry Office")
            self.assertIn('val="5B9BD5"', query_payload["themes"]["parts"][0]["xml"])

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
            self.assertFalse(any(item["surface"] == "charts" for item in payload["unsupported"]))
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
    def test_powershell_cli_accepts_visual_object_resource_actions(self) -> None:
        for resource, action in [
            ("chart-sheet", "list"),
            ("chart-sheet", "export"),
            ("connection", "update"),
            ("connection", "delete"),
            ("shape", "create"),
            ("shape", "delete"),
            ("picture", "add"),
            ("picture", "delete"),
            ("control", "list"),
            ("control", "get"),
            ("threaded-comment", "list"),
            ("privacy", "inspect"),
            ("privacy", "redact"),
            ("pivot-chart", "list"),
            ("pivot-chart", "export"),
        ]:
            with self.subTest(resource=resource, action=action):
                proc = run_pwsh_file(resource, action, "--workbook-path", str(FIXTURE_WORKBOOK), "--help")
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                combined = proc.stdout + proc.stderr
                self.assertIn("Usage:", combined)
                self.assertNotIn("unknown action", combined.lower())

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_powershell_cli_accepts_what_if_and_formula_audit_resource_actions(self) -> None:
        for resource, action in [
            ("what-if", "inspect"),
            ("scenario", "list"),
            ("scenario", "get"),
            ("scenario", "set"),
            ("scenario", "delete"),
            ("goal-seek", "execute"),
            ("solver", "inspect"),
            ("solver", "execute"),
            ("forecast-sheet", "plan"),
            ("forecast-sheet", "create"),
            ("data-table", "list"),
            ("data-table", "create"),
            ("formula-audit", "inspect"),
            ("formula-audit", "export"),
            ("calc-engine", "inspect"),
            ("calc-engine", "recalculate"),
            ("cube-function", "inspect"),
            ("lambda-name", "set"),
            ("sparkline", "create"),
            ("xml-map", "export"),
            ("custom-xml", "inspect"),
            ("ole-object", "export"),
            ("external-data-range", "refresh"),
            ("workbook-view", "update"),
            ("signature", "inspect"),
            ("encryption", "plan"),
            ("sensitivity", "inspect"),
        ]:
            with self.subTest(resource=resource, action=action):
                proc = run_pwsh_file(resource, action, "--workbook-path", str(FIXTURE_WORKBOOK), "--help")
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                combined = proc.stdout + proc.stderr
                self.assertIn("Usage:", combined)
                self.assertNotIn("unknown action", combined.lower())

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_powershell_cli_accepts_cloud_resource_actions(self) -> None:
        for resource, action in [
            ("graph-workbook", "worksheet-get"),
            ("graph-workbook", "worksheet-update"),
            ("graph-workbook", "range-clear"),
            ("graph-workbook", "range-format-get"),
            ("graph-workbook", "range-format-set"),
            ("graph-workbook", "range-format-font-set"),
            ("graph-workbook", "range-format-fill-set"),
            ("graph-workbook", "range-format-autofit-columns"),
            ("graph-workbook", "name-list"),
            ("graph-workbook", "name-get"),
            ("graph-workbook", "name-create"),
            ("graph-workbook", "name-update"),
            ("graph-workbook", "name-delete"),
            ("graph-workbook", "table-get"),
            ("graph-workbook", "table-row-add"),
            ("graph-workbook", "table-sort-apply"),
            ("graph-workbook", "table-filter-clear"),
            ("graph-workbook", "chart-get"),
            ("graph-workbook", "chart-update"),
            ("graph-workbook", "chart-delete"),
            ("graph-workbook", "chart-image"),
            ("graph-workbook", "chart-set-data"),
            ("graph-workbook", "function-call"),
            ("graph-workbook", "protection-get"),
            ("graph-workbook", "protection-protect"),
            ("graph-workbook", "protection-unprotect"),
            ("fabric-semantic-model", "get-definition"),
            ("fabric-semantic-model", "operation-get"),
            ("semantic-artifact", "inspect"),
            ("model-measure", "set"),
            ("office-script-live", "plan"),
            ("office-script-live", "execute"),
            ("addin-runtime", "validate"),
            ("addin-runtime", "sideload-plan"),
        ]:
            with self.subTest(resource=resource, action=action):
                proc = run_pwsh_file(resource, action, "--help")
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                combined = proc.stdout + proc.stderr
                self.assertIn("Usage:", combined)
                self.assertNotIn("unknown action", combined.lower())

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_direct_what_if_commands_require_expected_arguments(self) -> None:
        proc = run_pwsh_file("goal-seek", "execute", "--workbook-path", str(FIXTURE_WORKBOOK))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("goal-seek execute requires --spec-json or --spec-file", (proc.stdout + proc.stderr).lower())

        export_proc = run_pwsh_file("formula-audit", "export", "--workbook-path", str(FIXTURE_WORKBOOK))
        self.assertNotEqual(export_proc.returncode, 0)
        self.assertIn("formula-audit export requires --target-path", (export_proc.stdout + export_proc.stderr).lower())

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
    def test_powershell_cli_accumulates_repeated_surface_flags_for_workbook_diff(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-repeated-surface-") as tmpdir:
            workbook = Path(tmpdir) / "generated.xlsm"
            build_minimal_ooxml_workbook(workbook)
            proc = run_pwsh_file(
                "workbook",
                "diff",
                "--workbook-path",
                str(workbook),
                "--other-workbook-path",
                str(workbook),
                "--surface",
                "workbook",
                "--surface",
                "sheets",
                "--surface",
                "names",
                timeout=120,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            surfaces = [entry["surface"] for entry in payload["surfaces"]]
            self.assertEqual(surfaces, ["workbook", "sheets", "names"])

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
    def test_workbook_compatibility_report_handles_sparse_counts(self) -> None:
        proc = run_pwsh(
            dedent(
                f"""
                . '{COMMON}'
                $inspection = [pscustomobject]@{{
                    workbookPath = 'C:\\temp\\report.xlsx'
                    sourceFormat = '.xlsx'
                    workbook = [pscustomobject]@{{
                        hasVbaProject = $false
                    }}
                    counts = [pscustomobject]@{{
                        sheets = 1
                        formulas = 0
                    }}
                }}
                Get-WorkbookCompatibilityReport -InspectionPayload $inspection -TargetFormat 'csv' | ConvertTo-Json -Compress -Depth 20
                """
            )
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["targetFormat"], "csv")
        self.assertIsInstance(payload["findings"], list)

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_package_helper_inspect_lite_returns_inventory_payload(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-inspect-lite-") as tmpdir:
            workbook = Path(tmpdir) / "generated.xlsm"
            build_minimal_ooxml_workbook(workbook)
            proc = run_pwsh(
                dedent(
                    f"""
                    . '{COMMON}'
                    $payload = Invoke-PackageWorkbookHelper -Command 'inspect-lite' -WorkbookPath '{workbook}'
                    $payload | ConvertTo-Json -Compress -Depth 50
                    """
                ),
                timeout=120,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["backend"], "package")
            self.assertEqual(Path(payload["workbookPath"]), workbook.resolve())
            self.assertGreaterEqual(payload["counts"]["sheets"], 1)
            self.assertIn("workbook", payload)
            self.assertIn("sheets", payload)

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_workbook_lifecycle_inspection_prefers_package_backend_for_ooxml(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-lifecycle-") as tmpdir:
            workbook = Path(tmpdir) / "generated.xlsm"
            build_minimal_ooxml_workbook(workbook)
            proc = run_pwsh(
                dedent(
                    f"""
                    . '{COMMON}'
                    $payload = Get-ExcelWorkbookLifecycleInspection -WorkbookPath '{workbook}' -Backend 'auto'
                    $payload | ConvertTo-Json -Compress -Depth 50
                    """
                ),
                timeout=120,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["backend"], "package")
            self.assertEqual(payload["sourceFormat"], ".xlsm")
            self.assertGreaterEqual(payload["counts"]["tables"], 1)
            self.assertFalse(payload["workbook"]["hasVbaProject"])

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_workbook_inspect_defaults_to_compact_inventory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-workbook-inspect-") as tmpdir:
            workbook = Path(tmpdir) / "generated.xlsm"
            build_minimal_ooxml_workbook(workbook)
            proc = run_pwsh_file(
                "workbook",
                "inspect",
                "--workbook-path",
                str(workbook),
                timeout=120,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["backend"], "package")
            self.assertIn("counts", payload)
            self.assertIn("workbook", payload)
            self.assertIn("sheets", payload)
            self.assertNotIn("tables", payload)
            self.assertNotIn("formulas", payload)

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_inspect_defaults_to_compact_inventory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-inspect-") as tmpdir:
            workbook = Path(tmpdir) / "generated.xlsm"
            build_minimal_ooxml_workbook(workbook)
            proc = run_pwsh_file(
                "inspect",
                "--workbook-path",
                str(workbook),
                "--backend",
                "package",
                timeout=120,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["backend"], "package")
            self.assertIn("counts", payload)
            self.assertIn("workbook", payload)
            self.assertIn("sheets", payload)
            self.assertNotIn("tables", payload)
            self.assertNotIn("formulas", payload)

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_direct_package_read_fallback_supports_query_and_connection_get(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-query-fallback-") as tmpdir:
            workbook = Path(tmpdir) / "generated.xlsm"
            build_minimal_ooxml_workbook(workbook)
            proc = run_pwsh(
                dedent(
                    f"""
                    . '{COMMON}'
                    $query = Invoke-DirectPackageReadFallback -Command 'query-get' -WorkbookPath '{workbook}' -QueryName @('Query1')
                    $connection = Invoke-DirectPackageReadFallback -Command 'connection-get' -WorkbookPath '{workbook}' -Connection @('Query - Query1')
                    [pscustomobject]@{{
                        queryBackend = $query.backend
                        queryName = $query.query.name
                        connectionBackend = $connection.backend
                        connectionName = $connection.connection.name
                    }} | ConvertTo-Json -Compress -Depth 20
                    """
                ),
                timeout=120,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["queryBackend"], "package")
            self.assertEqual(payload["queryName"], "Query1")
            self.assertEqual(payload["connectionBackend"], "package")
            self.assertEqual(payload["connectionName"], "Query - Query1")

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_direct_package_read_fallback_supports_table_get(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-table-fallback-") as tmpdir:
            workbook = Path(tmpdir) / "generated.xlsm"
            build_minimal_ooxml_workbook(workbook)
            proc = run_pwsh(
                dedent(
                    f"""
                    . '{COMMON}'
                    $table = Invoke-DirectPackageReadFallback -Command 'table-get' -WorkbookPath '{workbook}' -Table @('Table1')
                    [pscustomobject]@{{
                        backend = $table.backend
                        name = $table.table.name
                    }} | ConvertTo-Json -Compress -Depth 20
                    """
                ),
                timeout=120,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["backend"], "package")
            self.assertEqual(payload["name"], "Table1")

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_direct_package_read_fallback_supports_chart_list_and_get(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-chart-fallback-") as tmpdir:
            workbook = Path(tmpdir) / "package-chart-workbook.xlsx"
            build_minimal_ooxml_workbook(workbook, include_chart=True)
            proc = run_pwsh(
                dedent(
                    f"""
                    . '{COMMON}'
                    $list = Invoke-DirectPackageReadFallback -Command 'chart-list' -WorkbookPath '{workbook}'
                    $chart = Invoke-DirectPackageReadFallback -Command 'chart-get' -WorkbookPath '{workbook}' -Chart @('Chart 1')
                    [pscustomobject]@{{
                        listBackend = $list.backend
                        listCount = @($list.charts).Count
                        chartBackend = $chart.backend
                        chartName = $chart.chart.name
                        chartTitle = $chart.chart.title
                    }} | ConvertTo-Json -Compress -Depth 20
                    """
                ),
                timeout=120,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["listBackend"], "package")
            self.assertEqual(payload["listCount"], 1)
            self.assertEqual(payload["chartBackend"], "package")
            self.assertEqual(payload["chartName"], "Chart 1")
            self.assertEqual(payload["chartTitle"], "Sales")

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
    def test_automation_artifact_workbook_generation_and_run_plan(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-automation-artifact-") as tmpdir:
            target = Path(tmpdir) / "build-workbook.mjs"
            spec = json.dumps({"sheets": ["Inputs", "Dashboard"], "outputPath": "generated.xlsx"})

            generate_proc = run_skill_cli(
                "automation",
                "generate",
                "--automation-type",
                "artifact-workbook",
                "--target-path",
                str(target),
                "--spec-json",
                spec,
                timeout=60,
            )
            self.assertEqual(generate_proc.returncode, 0, generate_proc.stdout + generate_proc.stderr)
            generate_payload = json.loads(generate_proc.stdout)
            self.assertEqual(generate_payload["automationType"], "artifact-workbook")
            self.assertTrue(target.exists())
            self.assertIn("@oai/artifact-tool", target.read_text(encoding="utf-8"))

            run_proc = run_skill_cli(
                "automation",
                "run",
                "--automation-type",
                "office-script",
                "--target-path",
                str(target),
                timeout=60,
            )
            self.assertEqual(run_proc.returncode, 0, run_proc.stdout + run_proc.stderr)
            run_payload = json.loads(run_proc.stdout)
            self.assertEqual(run_payload["status"], "runner-plan")
            self.assertEqual(run_payload["automationType"], "office-script")

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_office_script_generation_emits_workbook_surface_api_calls(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-office-script-surfaces-") as tmpdir:
            target = Path(tmpdir) / "workbook-surfaces.ts"
            spec = json.dumps(
                {
                    "name": "Workbook Surface Script",
                    "operations": [
                        "apply-conditional-format",
                        "apply-data-validation",
                        "add-comment",
                        "table-upsert",
                        "worksheet-upsert",
                        "format-range",
                        "protect-worksheet",
                    ],
                }
            )
            generate_proc = run_skill_cli(
                "automation",
                "generate",
                "--automation-type",
                "office-script",
                "--target-path",
                str(target),
                "--spec-json",
                spec,
                timeout=60,
            )
            self.assertEqual(generate_proc.returncode, 0, generate_proc.stdout + generate_proc.stderr)
            payload = json.loads(generate_proc.stdout)
            self.assertEqual(payload["automationType"], "office-script")
            self.assertEqual(payload["operations"], json.loads(spec)["operations"])
            script = target.read_text(encoding="utf-8")
            for expected in [
                "addConditionalFormat",
                "getDataValidation().setRule",
                "workbook.addComment",
                "sheet.addTable",
                "workbook.addWorksheet",
                "format.autofitColumns",
                "getProtection().protect",
            ]:
                self.assertIn(expected, script)

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_automation_public_aliases_return_host_plans(self) -> None:
        for resource, action, automation_type in [
            ("office-script", "validate", "office-script"),
            ("office-script", "run-plan", "office-script"),
            ("excel-js-api", "validate", "excel-js-api"),
            ("excel-js-api", "run-plan", "excel-js-api"),
            ("office-addin", "validate", "office-addin"),
            ("office-addin", "sideload-plan", "office-addin"),
        ]:
            with self.subTest(resource=resource, action=action):
                proc = run_skill_cli(resource, action, timeout=60)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                payload = json.loads(proc.stdout)
                self.assertEqual(payload["status"], "runner-plan")
                self.assertEqual(payload["automationType"], automation_type)
                self.assertIn("operation", payload)

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_host_limited_public_aliases_return_standard_envelope(self) -> None:
        for resource, action in [
            ("chart-sheet", "export"),
            ("threaded-comment", "create"),
            ("privacy", "redact"),
            ("pivot-chart", "export"),
        ]:
            with self.subTest(resource=resource, action=action):
                proc = run_skill_cli(resource, action, "--workbook-path", str(FIXTURE_WORKBOOK), timeout=60)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                payload = json.loads(proc.stdout)
                self.assertEqual(payload["status"], "host-limited")
                for field in ["backend", "operation", "changed", "readback", "warnings", "limitations", "secretHandling"]:
                    self.assertIn(field, payload)

    def test_cloud_graph_workbook_commands_require_runtime_token_and_build_dry_run_requests(self) -> None:
        package_module = load_package_module("excel_workbook_package_for_cloud_graph")
        missing = package_module.run_graph_workbook_command(
            argparse.Namespace(
                command="graph-workbook-worksheet-list",
                item_id="workbook_example",
                drive_id=None,
                item_path=None,
                session_id=None,
                spec_json=None,
                spec_file=None,
                dry_run=False,
            )
        )
        self.assertEqual(missing["status"], "host-limited")
        self.assertFalse(missing["changed"])
        self.assertTrue(any("EXCEL_FOUNDRY_GRAPH_TOKEN" in item for item in missing["warnings"]))

        old_token = os.environ.get("EXCEL_FOUNDRY_GRAPH_TOKEN")
        os.environ["EXCEL_FOUNDRY_GRAPH_TOKEN"] = "graph_redaction_probe"
        try:
            dry_run = package_module.run_graph_workbook_command(
                argparse.Namespace(
                    command="graph-workbook-range-set",
                    item_id="workbook_example",
                    drive_id=None,
                    item_path=None,
                    session_id="session_example",
                    sheet=["Sheet1"],
                    address=None,
                    range_ref="A1:B1",
                    value_json=None,
                    values_json=json.dumps([[1, 2]]),
                    spec_json=None,
                    spec_file=None,
                    dry_run=True,
                    persist_changes=False,
                    deep=False,
                )
            )
        finally:
            if old_token is None:
                os.environ.pop("EXCEL_FOUNDRY_GRAPH_TOKEN", None)
            else:
                os.environ["EXCEL_FOUNDRY_GRAPH_TOKEN"] = old_token
        self.assertEqual(dry_run["status"], "dry-run")
        self.assertEqual(dry_run["request"]["method"], "PATCH")
        self.assertIn("/workbook/worksheets/", dry_run["request"]["url"])
        self.assertIn("range(address=", dry_run["request"]["url"])
        self.assertEqual(dry_run["request"]["headers"]["Workbook-Session-Id"], "session_example")
        self.assertEqual(dry_run["request"]["body"]["values"], [[1, 2]])
        self.assertNotIn("graph_redaction_probe", json.dumps(dry_run))

        old_token = os.environ.get("EXCEL_FOUNDRY_GRAPH_TOKEN")
        os.environ["EXCEL_FOUNDRY_GRAPH_TOKEN"] = "graph_redaction_probe"
        try:
            graph_cases = [
                (
                    "graph-workbook-worksheet-update",
                    {"sheet": ["Sheet1"], "spec_json": json.dumps({"name": "Renamed"})},
                    "PATCH",
                    "/worksheets/",
                ),
                (
                    "graph-workbook-range-clear",
                    {"sheet": ["Sheet1"], "range_ref": "A1:B1", "spec_json": json.dumps({"applyTo": "Contents"})},
                    "POST",
                    "/clear",
                ),
                (
                    "graph-workbook-range-format-set",
                    {"sheet": ["Sheet1"], "range_ref": "A1:B1", "spec_json": json.dumps({"columnWidth": 18})},
                    "PATCH",
                    "/format",
                ),
                (
                    "graph-workbook-range-format-font-set",
                    {"sheet": ["Sheet1"], "range_ref": "A1:B1", "spec_json": json.dumps({"bold": True})},
                    "PATCH",
                    "/format/font",
                ),
                (
                    "graph-workbook-range-format-fill-set",
                    {"sheet": ["Sheet1"], "range_ref": "A1:B1", "spec_json": json.dumps({"color": "#D9EAF7"})},
                    "PATCH",
                    "/format/fill",
                ),
                (
                    "graph-workbook-range-format-autofit-columns",
                    {"sheet": ["Sheet1"], "range_ref": "A1:B1"},
                    "POST",
                    "/format/autofitColumns",
                ),
                (
                    "graph-workbook-name-create",
                    {"name": ["NamedInput"], "range_ref": "Sheet1!A1"},
                    "POST",
                    "/names/add",
                ),
                (
                    "graph-workbook-name-update",
                    {"name": ["NamedInput"], "range_ref": "Sheet1!B1"},
                    "PATCH",
                    "/names/",
                ),
                (
                    "graph-workbook-name-delete",
                    {"name": ["NamedInput"]},
                    "POST",
                    "/delete",
                ),
                (
                    "graph-workbook-table-get",
                    {"table": ["Table1"]},
                    "GET",
                    "/tables/",
                ),
                (
                    "graph-workbook-table-row-add",
                    {"table": ["Table1"], "spec_json": json.dumps({"values": [["Alpha", 1]]})},
                    "POST",
                    "/rows/add",
                ),
                (
                    "graph-workbook-table-column-add",
                    {"table": ["Table1"], "spec_json": json.dumps({"values": [["NewColumn"]]})},
                    "POST",
                    "/columns/add",
                ),
                (
                    "graph-workbook-table-sort-apply",
                    {"table": ["Table1"], "spec_json": json.dumps({"fields": [{"key": 1, "ascending": True}]})},
                    "POST",
                    "/sort/apply",
                ),
                (
                    "graph-workbook-table-filter-clear",
                    {"table": ["Table1"], "name": ["Value"]},
                    "POST",
                    "/filter/clear",
                ),
                (
                    "graph-workbook-table-convert-to-range",
                    {"table": ["Table1"]},
                    "POST",
                    "/convertToRange",
                ),
                (
                    "graph-workbook-chart-update",
                    {"sheet": ["Sheet1"], "name": ["Chart 1"], "spec_json": json.dumps({"name": "Chart 2"})},
                    "PATCH",
                    "/charts/",
                ),
                (
                    "graph-workbook-chart-image",
                    {"sheet": ["Sheet1"], "name": ["Chart 1"], "spec_json": json.dumps({"width": 640, "height": 480})},
                    "POST",
                    "/image",
                ),
                (
                    "graph-workbook-chart-set-data",
                    {"sheet": ["Sheet1"], "name": ["Chart 1"], "spec_json": json.dumps({"sourceData": "A1:B2", "seriesBy": "Auto"})},
                    "POST",
                    "/setData",
                ),
                (
                    "graph-workbook-function-call",
                    {"name": ["sum"], "spec_json": json.dumps({"values": [[1, 2, 3]]})},
                    "POST",
                    "/functions/sum",
                ),
                (
                    "graph-workbook-chart-delete",
                    {"sheet": ["Sheet1"], "name": ["Chart 1"]},
                    "POST",
                    "/delete",
                ),
                (
                    "graph-workbook-protection-protect",
                    {"sheet": ["Sheet1"], "spec_json": json.dumps({"options": {"allowFormatCells": True}})},
                    "POST",
                    "/protection/protect",
                ),
                (
                    "graph-workbook-protection-unprotect",
                    {"sheet": ["Sheet1"]},
                    "POST",
                    "/protection/unprotect",
                ),
            ]
            for command, overrides, method, url_fragment in graph_cases:
                with self.subTest(command=command):
                    base_args = {
                        "command": command,
                        "item_id": "workbook_example",
                        "drive_id": None,
                        "item_path": None,
                        "session_id": "session_example",
                        "sheet": [],
                        "table": [],
                        "name": [],
                        "address": None,
                        "range_ref": None,
                        "value_json": None,
                        "values_json": None,
                        "spec_json": None,
                        "spec_file": None,
                        "dry_run": True,
                        "persist_changes": False,
                        "deep": False,
                    }
                    base_args.update(overrides)
                    payload = package_module.run_graph_workbook_command(argparse.Namespace(**base_args))
                    self.assertEqual(payload["status"], "dry-run")
                    self.assertEqual(payload["request"]["method"], method)
                    self.assertIn(url_fragment, payload["request"]["url"])
                    self.assertEqual(payload["request"]["headers"]["Workbook-Session-Id"], "session_example")
                    self.assertNotIn("graph_redaction_probe", json.dumps(payload))
        finally:
            if old_token is None:
                os.environ.pop("EXCEL_FOUNDRY_GRAPH_TOKEN", None)
            else:
                os.environ["EXCEL_FOUNDRY_GRAPH_TOKEN"] = old_token

    def test_cloud_powerbi_dax_and_fabric_commands_build_dry_run_requests(self) -> None:
        package_module = load_package_module("excel_workbook_package_for_cloud_powerbi")
        old_powerbi = os.environ.get("EXCEL_FOUNDRY_POWERBI_TOKEN")
        old_fabric = os.environ.get("EXCEL_FOUNDRY_FABRIC_TOKEN")
        os.environ["EXCEL_FOUNDRY_POWERBI_TOKEN"] = "powerbi_redaction_probe"
        os.environ["EXCEL_FOUNDRY_FABRIC_TOKEN"] = "fabric_redaction_probe"
        try:
            dax = package_module.run_dax_command(
                argparse.Namespace(
                    command="dax-execute",
                    workspace_id="workspace_example",
                    dataset_id="dataset_example",
                    semantic_model_id=None,
                    dax_query='EVALUATE ROW("A", 1)',
                    spec_json=None,
                    spec_file=None,
                    dry_run=True,
                )
            )
            fabric = package_module.run_fabric_semantic_command(
                argparse.Namespace(
                    command="fabric-semantic-model-get-definition",
                    workspace_id="workspace_example",
                    semantic_model_id="model_example",
                    dataset_id=None,
                    operation_id=None,
                    operation_location=None,
                    definition_dir=None,
                    output_dir=None,
                    format="TMDL",
                    spec_json=None,
                    spec_file=None,
                    dry_run=True,
                    deep=False,
                )
            )
        finally:
            if old_powerbi is None:
                os.environ.pop("EXCEL_FOUNDRY_POWERBI_TOKEN", None)
            else:
                os.environ["EXCEL_FOUNDRY_POWERBI_TOKEN"] = old_powerbi
            if old_fabric is None:
                os.environ.pop("EXCEL_FOUNDRY_FABRIC_TOKEN", None)
            else:
                os.environ["EXCEL_FOUNDRY_FABRIC_TOKEN"] = old_fabric

        self.assertEqual(dax["status"], "dry-run")
        self.assertIn("/executeQueries", dax["request"]["url"])
        self.assertEqual(dax["request"]["body"]["queries"][0]["query"], 'EVALUATE ROW("A", 1)')
        self.assertNotIn("powerbi_redaction_probe", json.dumps(dax))
        self.assertEqual(fabric["status"], "dry-run")
        self.assertIn("/semanticModels/model_example/getDefinition", fabric["request"]["url"])
        self.assertEqual(fabric["request"]["body"]["format"], "TMDL")
        self.assertNotIn("fabric_redaction_probe", json.dumps(fabric))

        old_fabric = os.environ.get("EXCEL_FOUNDRY_FABRIC_TOKEN")
        os.environ["EXCEL_FOUNDRY_FABRIC_TOKEN"] = "fabric_redaction_probe"
        try:
            operation_poll = package_module.run_fabric_semantic_command(
                argparse.Namespace(
                    command="fabric-semantic-model-operation-get",
                    workspace_id=None,
                    semantic_model_id=None,
                    dataset_id=None,
                    operation_id="operation_example",
                    operation_location=None,
                    definition_dir=None,
                    output_dir=None,
                    format=None,
                    spec_json=None,
                    spec_file=None,
                    dry_run=True,
                    deep=False,
                )
            )
            operation_result = package_module.run_fabric_semantic_command(
                argparse.Namespace(
                    command="fabric-semantic-model-operation-result",
                    workspace_id=None,
                    semantic_model_id=None,
                    dataset_id=None,
                    operation_id=None,
                    operation_location="https://api.fabric.microsoft.com/v1/operations/operation_example",
                    definition_dir=None,
                    output_dir=None,
                    format=None,
                    spec_json=None,
                    spec_file=None,
                    dry_run=True,
                    deep=False,
                )
            )
        finally:
            if old_fabric is None:
                os.environ.pop("EXCEL_FOUNDRY_FABRIC_TOKEN", None)
            else:
                os.environ["EXCEL_FOUNDRY_FABRIC_TOKEN"] = old_fabric
        self.assertEqual(operation_poll["request"]["method"], "GET")
        self.assertTrue(operation_poll["request"]["url"].endswith("/operations/operation_example"))
        self.assertTrue(operation_result["request"]["url"].endswith("/operations/operation_example/result"))
        self.assertNotIn("fabric_redaction_probe", json.dumps(operation_poll) + json.dumps(operation_result))

        old_fabric = os.environ.get("EXCEL_FOUNDRY_FABRIC_TOKEN")
        os.environ["EXCEL_FOUNDRY_FABRIC_TOKEN"] = "fabric_redaction_probe"
        original_http = package_module._cloud_http_json
        try:
            package_module._cloud_http_json = lambda *args, **kwargs: {
                "statusCode": 202,
                "headers": {"Location": "https://api.fabric.microsoft.com/operations/example", "Retry-After": "30"},
                "body": None,
            }
            accepted = package_module.run_fabric_semantic_command(
                argparse.Namespace(
                    command="fabric-semantic-model-get-definition",
                    workspace_id="workspace_example",
                    semantic_model_id="model_example",
                    dataset_id=None,
                    operation_id=None,
                    operation_location=None,
                    definition_dir=None,
                    output_dir=None,
                    format="TMDL",
                    spec_json=None,
                    spec_file=None,
                    dry_run=False,
                    deep=False,
                )
            )
        finally:
            package_module._cloud_http_json = original_http
            if old_fabric is None:
                os.environ.pop("EXCEL_FOUNDRY_FABRIC_TOKEN", None)
            else:
                os.environ["EXCEL_FOUNDRY_FABRIC_TOKEN"] = old_fabric
        self.assertEqual(accepted["status"], "accepted")
        self.assertEqual(accepted["operationLocation"], "https://api.fabric.microsoft.com/operations/example")
        self.assertEqual(accepted["retryAfter"], "30")

    def test_cloud_semantic_artifact_commands_inventory_and_plan_definition_parts(self) -> None:
        package_module = load_package_module("excel_workbook_package_for_cloud_artifacts")
        with tempfile.TemporaryDirectory(prefix="excel-foundry-semantic-artifact-") as tmpdir:
            definition_root = Path(tmpdir) / "definition"
            table_dir = definition_root / "tables"
            table_dir.mkdir(parents=True)
            (definition_root / "model.tmdl").write_text("model Example\n", encoding="utf-8")
            (table_dir / "Sales.tmdl").write_text("table Sales\n", encoding="utf-8")

            inspect_payload = package_module.run_semantic_artifact_command(
                argparse.Namespace(
                    command="semantic-artifact-inspect",
                    definition_dir=str(definition_root),
                    target_path=None,
                )
            )
            self.assertEqual(inspect_payload["status"], "completed")
            self.assertEqual(inspect_payload["readback"]["partCount"], 2)
            self.assertTrue(any(part["path"] == "tables/Sales.tmdl" for part in inspect_payload["parts"]))

            old_fabric = os.environ.get("EXCEL_FOUNDRY_FABRIC_TOKEN")
            os.environ["EXCEL_FOUNDRY_FABRIC_TOKEN"] = "fabric_redaction_probe"
            try:
                model_table = package_module.run_model_table_command(
                    argparse.Namespace(
                        command="model-table-set",
                        workspace_id="workspace_example",
                        semantic_model_id="model_example",
                        dataset_id=None,
                        definition_dir=str(definition_root),
                        output_dir=None,
                        format="TMDL",
                        spec_json=None,
                        spec_file=None,
                        dry_run=True,
                        deep=False,
                    )
                )
            finally:
                if old_fabric is None:
                    os.environ.pop("EXCEL_FOUNDRY_FABRIC_TOKEN", None)
                else:
                    os.environ["EXCEL_FOUNDRY_FABRIC_TOKEN"] = old_fabric
            self.assertEqual(model_table["status"], "dry-run")
            self.assertIn("/updateDefinition", model_table["request"]["url"])
            part_summaries = model_table["request"]["body"]["definition"]["parts"]
            self.assertTrue(any(part["path"] == "tables/Sales.tmdl" and "bytes" in part for part in part_summaries))
            self.assertNotIn("fabric_redaction_probe", json.dumps(model_table))

            local_measure = package_module.run_tmdl_artifact_command(
                argparse.Namespace(
                    command="model-measure-set",
                    definition_dir=str(definition_root),
                    target_path=None,
                    name=["Gross Margin"],
                    spec_json=json.dumps({"table": "Sales", "expression": "SUM(Sales[Amount])"}),
                    spec_file=None,
                ),
                "measure",
            )
            local_relationship = package_module.run_tmdl_artifact_command(
                argparse.Namespace(
                    command="model-relationship-set",
                    definition_dir=str(definition_root),
                    target_path=None,
                    name=["Sales to Region"],
                    spec_json=json.dumps(
                        {
                            "fromTable": "Sales",
                            "fromColumn": "RegionId",
                            "toTable": "Region",
                            "toColumn": "RegionId",
                        }
                    ),
                    spec_file=None,
                ),
                "relationship",
            )
            self.assertTrue(local_measure["changed"])
            self.assertTrue((definition_root / "tables" / "Sales" / "measures" / "Gross-Margin.tmdl").exists())
            self.assertIn("relationship Sales-to-Region", (definition_root / "relationships" / "Sales-to-Region.tmdl").read_text(encoding="utf-8"))
            self.assertEqual(local_relationship["readback"]["path"], "relationships/Sales-to-Region.tmdl")

            old_fabric = os.environ.get("EXCEL_FOUNDRY_FABRIC_TOKEN")
            os.environ["EXCEL_FOUNDRY_FABRIC_TOKEN"] = "fabric_redaction_probe"
            original_http = package_module._cloud_http_json
            try:
                package_module._cloud_http_json = lambda *args, **kwargs: {
                    "statusCode": 200,
                    "headers": {"x-ms-operation-id": "operation-id"},
                    "body": {
                        "definition": {
                            "parts": [
                                {
                                    "path": "model.tmdl",
                                    "payloadType": "InlineBase64",
                                    "payload": base64.b64encode(b"model Exported\n").decode("ascii"),
                                }
                            ]
                        }
                    },
                }
                export_dir = Path(tmpdir) / "export"
                exported = package_module.run_fabric_semantic_command(
                    argparse.Namespace(
                        command="fabric-semantic-model-export-definition",
                        workspace_id="workspace_example",
                        semantic_model_id="model_example",
                        dataset_id=None,
                        definition_dir=None,
                        output_dir=str(export_dir),
                        format="TMDL",
                        spec_json=None,
                        spec_file=None,
                        dry_run=False,
                        deep=False,
                    )
                )
            finally:
                package_module._cloud_http_json = original_http
                if old_fabric is None:
                    os.environ.pop("EXCEL_FOUNDRY_FABRIC_TOKEN", None)
                else:
                    os.environ["EXCEL_FOUNDRY_FABRIC_TOKEN"] = old_fabric
            self.assertEqual(exported["status"], "completed")
            self.assertEqual((export_dir / "model.tmdl").read_text(encoding="utf-8"), "model Exported\n")

            with self.assertRaises(ValueError):
                package_module._write_definition_parts(
                    str(Path(tmpdir) / "blocked-export"),
                    [
                        {
                            "path": "../escape.tmdl",
                            "payloadType": "InlineBase64",
                            "payload": base64.b64encode(b"escape").decode("ascii"),
                        }
                    ],
                )

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_direct_model_commands_support_guarded_mutation_plans(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-model-plan-") as tmpdir:
            workbook = Path(tmpdir) / "model.xlsx"
            build_minimal_ooxml_workbook(workbook)
            set_commands = [
                ("measure", "set", {"name": "Gross Margin", "associatedTable": "Sales", "formula": "=SUM(Sales[Amount])"}),
                (
                    "relationship",
                    "set",
                    {
                        "foreignKeyTable": "Sales",
                        "foreignKeyColumn": "RegionId",
                        "primaryKeyTable": "Regions",
                        "primaryKeyColumn": "RegionId",
                    },
                ),
                ("hierarchy", "set", {"name": "RegionHierarchy", "levels": ["Region", "District"]}),
                ("kpi", "set", {"name": "MarginKpi", "measure": "Gross Margin"}),
                ("perspective", "set", {"name": "Executive", "tables": ["Sales"]}),
            ]
            for resource, action, spec in set_commands:
                proc = run_skill_cli(resource, action, "--workbook-path", str(workbook), "--spec-json", json.dumps(spec), timeout=60)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                payload = json.loads(proc.stdout)
                self.assertEqual(payload["status"], "platform-limited")
                self.assertFalse(payload["changed"])
                self.assertTrue(payload["name"])

            for resource, name in [
                ("measure", "Gross Margin"),
                ("relationship", "Sales[RegionId]->Regions[RegionId]"),
                ("hierarchy", "RegionHierarchy"),
                ("kpi", "MarginKpi"),
                ("perspective", "Executive"),
            ]:
                proc = run_skill_cli(resource, "delete", "--workbook-path", str(workbook), "--name", name, timeout=60)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                payload = json.loads(proc.stdout)
                self.assertEqual(payload["status"], "platform-limited")
                self.assertEqual(payload["name"], name)

    @unittest.skipUnless(HAS_PWSH, "pwsh not available on this host")
    def test_powershell_scripts_parse_cleanly(self) -> None:
        for script in [
            ROOT / "scripts" / "excel-foundry.ps1",
            ROOT / "scripts" / "ExcelFoundry.Common.ps1",
            ROOT / "scripts" / "ExcelSync.Common.ps1",
            ROOT / "scripts" / "sync-foundry.ps1",
            ROOT / "scripts" / "sync-foundry-powerquery.ps1",
            ROOT / "scripts" / "sync-foundry-vba.ps1",
            ROOT / "scripts" / "sync-foundry-structure.ps1",
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

    @unittest.skipUnless(LIVE_DESKTOP_MUTATION, "set EXCEL_FOUNDRY_LIVE_DESKTOP=1 and EXCEL_FOUNDRY_LIVE_MUTATION=1 to run live Excel COM mutation tests")
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

    @unittest.skipUnless(LIVE_DESKTOP_MUTATION, "set EXCEL_FOUNDRY_LIVE_DESKTOP=1 and EXCEL_FOUNDRY_LIVE_MUTATION=1 to run live Excel COM mutation tests")
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

    @unittest.skipUnless(LIVE_DESKTOP_MUTATION, "set EXCEL_FOUNDRY_LIVE_DESKTOP=1 and EXCEL_FOUNDRY_LIVE_MUTATION=1 to run live Excel COM mutation tests")
    def test_live_roundtrip_on_temp_workspace_copy(self) -> None:
        if not FIXTURE_WORKBOOK.exists():
            self.skipTest("fixture workbook is unavailable")

        with tempfile.TemporaryDirectory(prefix="excel-foundry-live-") as tmpdir:
            tmp_root = Path(tmpdir) / "workspace"
            shutil.copytree(FIXTURE_DIR, tmp_root)
            manifest = tmp_root / "excel-sync.manifest.json"
            workbook = tmp_root / "workflow_fixture.xlsm"

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

    @unittest.skipUnless(LIVE_DESKTOP_MUTATION, "set EXCEL_FOUNDRY_LIVE_DESKTOP=1 and EXCEL_FOUNDRY_LIVE_MUTATION=1 to run live Excel COM mutation tests")
    def test_live_vba_push_then_pull_roundtrips_module_change(self) -> None:
        if not FIXTURE_WORKBOOK.exists():
            self.skipTest("fixture workbook is unavailable")

        with tempfile.TemporaryDirectory(prefix="excel-foundry-live-vba-") as tmpdir:
            tmp_root = Path(tmpdir) / "workspace"
            shutil.copytree(FIXTURE_DIR, tmp_root)
            manifest = tmp_root / "excel-sync.manifest.json"
            workbook = tmp_root / "workflow_fixture.xlsm"
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

    @unittest.skipUnless(LIVE_DESKTOP_MUTATION, "set EXCEL_FOUNDRY_LIVE_DESKTOP=1 and EXCEL_FOUNDRY_LIVE_MUTATION=1 to run live Excel COM mutation tests")
    def test_live_vba_push_then_pull_roundtrips_self_contained_module(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-live-vba-self-contained-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "vba-probe.xlsm"
            manifest = tmp / "excel-sync.manifest.json"
            module_path = tmp / "modLiveProbe.bas"
            module_text = dedent(
                """\
                Attribute VB_Name = "modLiveProbe"
                Option Explicit
                Public Function LiveProbeValue() As String
                    LiveProbeValue = "initial"
                End Function
                """
            )
            module_path.write_text(module_text, encoding="utf-8")
            manifest.write_text(
                json.dumps(
                    {
                        "workbookPath": workbook.name,
                        "vbaComponents": [
                            {"name": "modLiveProbe", "path": module_path.name},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            create_proc = run_pwsh(
                dedent(
                    f"""
                    $excel = New-Object -ComObject Excel.Application
                    $excel.Visible = $false
                    $excel.DisplayAlerts = $false
                    $workbook = $excel.Workbooks.Add()
                    try {{
                        $workbook.SaveAs('{workbook}', 52)
                    }}
                    finally {{
                        $workbook.Close($false)
                        $excel.Quit()
                        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($workbook)
                        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
                    }}
                    """
                ),
                timeout=300,
            )
            self.assertEqual(create_proc.returncode, 0, create_proc.stdout + create_proc.stderr)

            push_proc = run_skill_cli("push", "--manifest-path", str(manifest), "--workbook-path", str(workbook), timeout=300)
            self.assertEqual(push_proc.returncode, 0, push_proc.stdout + push_proc.stderr)
            self.assertIn("PUSH VBA modLiveProbe", push_proc.stdout)

            module_path.write_text(module_text.replace('"initial"', '"local-reset"'), encoding="utf-8")

            pull_proc = run_skill_cli("pull", "--manifest-path", str(manifest), "--workbook-path", str(workbook), timeout=300)
            self.assertEqual(pull_proc.returncode, 0, pull_proc.stdout + pull_proc.stderr)
            self.assertIn("PULL VBA modLiveProbe", pull_proc.stdout)
            self.assertIn('LiveProbeValue = "initial"', module_path.read_text(encoding="utf-8"))

    @unittest.skipUnless(LIVE_DESKTOP_MUTATION, "set EXCEL_FOUNDRY_LIVE_DESKTOP=1 and EXCEL_FOUNDRY_LIVE_MUTATION=1 to run live Excel COM mutation tests")
    def test_live_cf_push_then_pull_roundtrips_new_rule(self) -> None:
        if not FIXTURE_WORKBOOK.exists():
            self.skipTest("fixture workbook is unavailable")

        with tempfile.TemporaryDirectory(prefix="excel-foundry-live-cf-") as tmpdir:
            tmp_root = Path(tmpdir) / "workspace"
            shutil.copytree(FIXTURE_DIR, tmp_root)
            manifest = tmp_root / "excel-sync.manifest.json"
            workbook = tmp_root / "workflow_fixture.xlsm"
            cf_path = tmp_root / "workbook_structure" / "conditional_formatting.json"

            artifact = json.loads(cf_path.read_text(encoding="utf-8"))
            artifact["rules"].append(
                {
                    "id": "CF-LIVE-TEST-0001",
                    "sheet": "DATA_RECORDS",
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
                    rule.get("sheet") == "DATA_RECORDS"
                    and rule.get("address") == "$C$5:$C$9"
                    and rule.get("formula") == "=TRUE"
                    for rule in pulled["rules"]
                )
            )

    @unittest.skipUnless(LIVE_DESKTOP_MUTATION, "set EXCEL_FOUNDRY_LIVE_DESKTOP=1 and EXCEL_FOUNDRY_LIVE_MUTATION=1 to run live Excel COM mutation tests")
    def test_live_powerquery_push_then_pull_roundtrips_formula_change(self) -> None:
        if not FIXTURE_WORKBOOK.exists():
            self.skipTest("fixture workbook is unavailable")

        with tempfile.TemporaryDirectory(prefix="excel-foundry-live-pq-") as tmpdir:
            tmp_root = Path(tmpdir) / "workspace"
            shutil.copytree(FIXTURE_DIR, tmp_root)
            manifest = tmp_root / "excel-sync.manifest.json"
            workbook = tmp_root / "workflow_fixture.xlsm"
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

    @unittest.skipUnless(LIVE_DESKTOP_MUTATION, "set EXCEL_FOUNDRY_LIVE_DESKTOP=1 and EXCEL_FOUNDRY_LIVE_MUTATION=1 to run live Excel COM mutation tests")
    def test_live_direct_table_commands_roundtrip(self) -> None:
        if not FIXTURE_WORKBOOK.exists():
            self.skipTest("fixture workbook is unavailable")

        with tempfile.TemporaryDirectory(prefix="excel-foundry-live-direct-table-") as tmpdir:
            workbook = Path(tmpdir) / "direct-table.xlsm"
            shutil.copy2(FIXTURE_WORKBOOK, workbook)
            create_spec = json.dumps(
                {
                    "sheet": "DATA_RECORDS",
                    "name": "LIVE_DIRECT_TABLE",
                    "topLeft": "Z1",
                    "headers": ["Code", "Amount"],
                    "rows": [["A100", 10], ["B200", 20]],
                }
            )
            update_spec = json.dumps(
                {
                    "sheet": "DATA_RECORDS",
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
            self.assertEqual(json.loads(get_proc.stdout)["table"]["sheet"], "DATA_RECORDS")

            update_proc = run_skill_cli("table", "update", "--workbook-path", str(workbook), "--spec-json", update_spec, timeout=300)
            self.assertEqual(update_proc.returncode, 0, update_proc.stdout + update_proc.stderr)
            self.assertEqual(len(json.loads(update_proc.stdout)["table"]["headers"]), 3)

            delete_proc = run_skill_cli("table", "delete", "--workbook-path", str(workbook), "--table", "LIVE_DIRECT_TABLE", timeout=300)
            self.assertEqual(delete_proc.returncode, 0, delete_proc.stdout + delete_proc.stderr)
            self.assertTrue(json.loads(delete_proc.stdout)["deleted"])

    @unittest.skipUnless(LIVE_DESKTOP_MUTATION, "set EXCEL_FOUNDRY_LIVE_DESKTOP=1 and EXCEL_FOUNDRY_LIVE_MUTATION=1 to run live Excel COM mutation tests")
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

    @unittest.skipUnless(LIVE_DESKTOP_MUTATION, "set EXCEL_FOUNDRY_LIVE_DESKTOP=1 and EXCEL_FOUNDRY_LIVE_MUTATION=1 to run live Excel COM mutation tests")
    def test_live_direct_query_set_accepts_minimal_spec(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-live-minimal-query-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "minimal-query.xlsx"
            create_proc = run_pwsh(
                dedent(
                    f"""
                    $excel = New-Object -ComObject Excel.Application
                    $excel.Visible = $false
                    $excel.DisplayAlerts = $false
                    $workbook = $excel.Workbooks.Add()
                    $workbook.SaveAs('{workbook}', 51)
                    $workbook.Close($false)
                    $excel.Quit()
                    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($workbook)
                    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
                    """
                ),
                timeout=300,
            )
            self.assertEqual(create_proc.returncode, 0, create_proc.stdout + create_proc.stderr)

            spec = json.dumps(
                {
                    "name": "LIVE_MINIMAL_QUERY",
                    "formula": "let Source = #table({\"Code\",\"Amount\"}, {{\"A\", 1}}) in Source",
                }
            )
            set_proc = run_skill_cli("query", "set", "--workbook-path", str(workbook), "--spec-json", spec, timeout=300)
            self.assertEqual(set_proc.returncode, 0, set_proc.stdout + set_proc.stderr)
            set_payload = json.loads(set_proc.stdout)
            self.assertEqual(set_payload["query"]["name"], "LIVE_MINIMAL_QUERY")
            self.assertEqual(set_payload["query"]["description"], "")

            get_proc = run_skill_cli("query", "get", "--workbook-path", str(workbook), "--query-name", "LIVE_MINIMAL_QUERY", timeout=300)
            self.assertEqual(get_proc.returncode, 0, get_proc.stdout + get_proc.stderr)
            get_payload = json.loads(get_proc.stdout)
            self.assertEqual(get_payload["query"]["name"], "LIVE_MINIMAL_QUERY")
            self.assertIn("Amount", get_payload["query"]["formula"])

    @unittest.skipUnless(LIVE_DESKTOP_MUTATION, "set EXCEL_FOUNDRY_LIVE_DESKTOP=1 and EXCEL_FOUNDRY_LIVE_MUTATION=1 to run live Excel COM mutation tests")
    def test_live_direct_connection_update_and_delete_commands_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-live-connection-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "direct-connection.xlsx"
            csv_path = tmp / "source.csv"
            csv_path.write_text("Code,Amount\nA,1\nB,2\n", encoding="ascii")
            create_proc = run_pwsh(
                dedent(
                    f"""
                    $excel = New-Object -ComObject Excel.Application
                    $excel.Visible = $false
                    $excel.DisplayAlerts = $false
                    $workbook = $excel.Workbooks.Add()
                    try {{
                        $sheet = $workbook.Worksheets.Item(1)
                        $sheet.Name = 'DATA'
                        $queryTable = $sheet.QueryTables.Add('TEXT;{csv_path}', $sheet.Range('A1'))
                        $queryTable.Name = 'LIVE_CONNECTION_SOURCE'
                        $queryTable.TextFileParseType = 1
                        $queryTable.TextFileCommaDelimiter = $true
                        [void]$queryTable.Refresh($false)
                        $workbook.Connections.Item('source').Description = 'original description'
                        $workbook.SaveAs('{workbook}', 51)
                    }}
                    finally {{
                        $workbook.Close($false)
                        $excel.Quit()
                        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($workbook)
                        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
                    }}
                    """
                ),
                timeout=300,
            )
            self.assertEqual(create_proc.returncode, 0, create_proc.stdout + create_proc.stderr)
            spec = json.dumps({"name": "source", "description": "updated description"})

            update_proc = run_skill_cli("connection", "update", "--workbook-path", str(workbook), "--spec-json", spec, timeout=300)
            self.assertEqual(update_proc.returncode, 0, update_proc.stdout + update_proc.stderr)
            update_payload = json.loads(update_proc.stdout)
            self.assertTrue(update_payload["changed"])
            self.assertEqual(update_payload["connection"]["description"], "updated description")

            get_proc = run_skill_cli("connection", "get", "--workbook-path", str(workbook), "--connection", "source", timeout=300)
            self.assertEqual(get_proc.returncode, 0, get_proc.stdout + get_proc.stderr)
            self.assertEqual(json.loads(get_proc.stdout)["connection"]["description"], "updated description")

            delete_proc = run_skill_cli("connection", "delete", "--workbook-path", str(workbook), "--connection", "source", timeout=300)
            self.assertEqual(delete_proc.returncode, 0, delete_proc.stdout + delete_proc.stderr)
            self.assertTrue(json.loads(delete_proc.stdout)["deleted"])

            list_proc = run_skill_cli("connection", "list", "--workbook-path", str(workbook), timeout=300)
            self.assertEqual(list_proc.returncode, 0, list_proc.stdout + list_proc.stderr)
            self.assertEqual(json.loads(list_proc.stdout)["connections"], [])

    @unittest.skipUnless(LIVE_DESKTOP_MUTATION, "set EXCEL_FOUNDRY_LIVE_DESKTOP=1 and EXCEL_FOUNDRY_LIVE_MUTATION=1 to run live Excel COM mutation tests")
    def test_live_direct_chart_and_pivot_list_commands_return_arrays(self) -> None:
        if not FIXTURE_WORKBOOK.exists():
            self.skipTest("fixture workbook is unavailable")

        chart_proc = run_skill_cli("chart", "list", "--workbook-path", str(FIXTURE_WORKBOOK), timeout=300)
        self.assertEqual(chart_proc.returncode, 0, chart_proc.stdout + chart_proc.stderr)
        self.assertIsInstance(json.loads(chart_proc.stdout)["charts"], list)

        pivot_proc = run_skill_cli("pivot", "list", "--workbook-path", str(FIXTURE_WORKBOOK), timeout=300)
        self.assertEqual(pivot_proc.returncode, 0, pivot_proc.stdout + pivot_proc.stderr)
        self.assertIsInstance(json.loads(pivot_proc.stdout)["pivots"], list)

    @unittest.skipUnless(LIVE_DESKTOP_MUTATION, "set EXCEL_FOUNDRY_LIVE_DESKTOP=1 and EXCEL_FOUNDRY_LIVE_MUTATION=1 to run live Excel COM mutation tests")
    def test_live_direct_pivot_commands_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-live-pivot-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "direct-pivot.xlsx"
            create_proc = run_pwsh(
                dedent(
                    f"""
                    $excel = New-Object -ComObject Excel.Application
                    $excel.Visible = $false
                    $excel.DisplayAlerts = $false
                    $workbook = $excel.Workbooks.Add()
                    try {{
                        $data = $workbook.Worksheets.Item(1)
                        $data.Name = 'DATA_RECORDS'
                        $data.Range('A1').Value2 = 'Region'
                        $data.Range('B1').Value2 = 'Category'
                        $data.Range('C1').Value2 = 'Amount'
                        $data.Range('A2').Value2 = 'West'
                        $data.Range('B2').Value2 = 'Hardware'
                        $data.Range('C2').Value2 = 10
                        $data.Range('A3').Value2 = 'West'
                        $data.Range('B3').Value2 = 'Software'
                        $data.Range('C3').Value2 = 20
                        $data.Range('A4').Value2 = 'East'
                        $data.Range('B4').Value2 = 'Hardware'
                        $data.Range('C4').Value2 = 30
                        $pivot = $workbook.Worksheets.Add()
                        $pivot.Name = 'PIVOTS'
                        $workbook.SaveAs('{workbook}', 51)
                    }}
                    finally {{
                        $workbook.Close($false)
                        $excel.Quit()
                        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($workbook)
                        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
                    }}
                    """
                ),
                timeout=120,
            )
            self.assertEqual(create_proc.returncode, 0, create_proc.stdout + create_proc.stderr)

            pivot_spec = json.dumps(
                {
                    "name": "LIVE_DIRECT_PIVOT",
                    "destinationSheet": "PIVOTS",
                    "topLeft": "A3",
                    "sourceSheet": "DATA_RECORDS",
                    "sourceAddress": "A1:C4",
                    "rowFields": ["Region"],
                    "dataFields": [{"name": "Amount", "summary": "sum", "caption": "Total Amount"}],
                }
            )
            update_spec = json.dumps(
                {
                    "name": "LIVE_DIRECT_PIVOT",
                    "destinationSheet": "PIVOTS",
                    "topLeft": "A3",
                    "sourceSheet": "DATA_RECORDS",
                    "sourceAddress": "A1:C4",
                    "rowFields": ["Category"],
                    "dataFields": [{"name": "Amount", "summary": "count", "caption": "Count Amount"}],
                }
            )

            create_pivot_proc = run_skill_cli("pivot", "create", "--workbook-path", str(workbook), "--spec-json", pivot_spec, timeout=300)
            self.assertEqual(create_pivot_proc.returncode, 0, create_pivot_proc.stdout + create_pivot_proc.stderr)
            created = json.loads(create_pivot_proc.stdout)["pivot"]
            self.assertEqual(created["name"], "LIVE_DIRECT_PIVOT")
            self.assertEqual(created["sheet"], "PIVOTS")

            get_pivot_proc = run_skill_cli("pivot", "get", "--workbook-path", str(workbook), "--pivot", "LIVE_DIRECT_PIVOT", timeout=300)
            self.assertEqual(get_pivot_proc.returncode, 0, get_pivot_proc.stdout + get_pivot_proc.stderr)
            self.assertEqual(json.loads(get_pivot_proc.stdout)["pivot"]["topLeft"], "A3")

            update_pivot_proc = run_skill_cli("pivot", "update", "--workbook-path", str(workbook), "--spec-json", update_spec, timeout=300)
            self.assertEqual(update_pivot_proc.returncode, 0, update_pivot_proc.stdout + update_pivot_proc.stderr)
            self.assertEqual(json.loads(update_pivot_proc.stdout)["pivot"]["name"], "LIVE_DIRECT_PIVOT")

            refresh_pivot_proc = run_skill_cli("pivot", "refresh", "--workbook-path", str(workbook), "--pivot", "LIVE_DIRECT_PIVOT", timeout=300)
            self.assertEqual(refresh_pivot_proc.returncode, 0, refresh_pivot_proc.stdout + refresh_pivot_proc.stderr)
            self.assertTrue(json.loads(refresh_pivot_proc.stdout)["refreshed"])

            delete_pivot_proc = run_skill_cli("pivot", "delete", "--workbook-path", str(workbook), "--pivot", "LIVE_DIRECT_PIVOT", timeout=300)
            self.assertEqual(delete_pivot_proc.returncode, 0, delete_pivot_proc.stdout + delete_pivot_proc.stderr)
            self.assertTrue(json.loads(delete_pivot_proc.stdout)["deleted"])

    @unittest.skipUnless(LIVE_DESKTOP_MUTATION, "set EXCEL_FOUNDRY_LIVE_DESKTOP=1 and EXCEL_FOUNDRY_LIVE_MUTATION=1 to run live Excel COM mutation tests")
    def test_live_direct_slicer_commands_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-live-slicer-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "direct-slicer.xlsx"
            create_proc = run_pwsh(
                dedent(
                    f"""
                    $excel = New-Object -ComObject Excel.Application
                    $excel.Visible = $false
                    $excel.DisplayAlerts = $false
                    $workbook = $excel.Workbooks.Add()
                    try {{
                        $data = $workbook.Worksheets.Item(1)
                        $data.Name = 'DATA_RECORDS'
                        $data.Range('A1').Value2 = 'Region'
                        $data.Range('B1').Value2 = 'Category'
                        $data.Range('C1').Value2 = 'Amount'
                        $data.Range('A2').Value2 = 'West'
                        $data.Range('B2').Value2 = 'Hardware'
                        $data.Range('C2').Value2 = 10
                        $data.Range('A3').Value2 = 'West'
                        $data.Range('B3').Value2 = 'Software'
                        $data.Range('C3').Value2 = 20
                        $data.Range('A4').Value2 = 'East'
                        $data.Range('B4').Value2 = 'Hardware'
                        $data.Range('C4').Value2 = 30
                        $pivot = $workbook.Worksheets.Add()
                        $pivot.Name = 'PIVOTS'
                        $workbook.SaveAs('{workbook}', 51)
                    }}
                    finally {{
                        $workbook.Close($false)
                        $excel.Quit()
                        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($workbook)
                        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
                    }}
                    """
                ),
                timeout=120,
            )
            self.assertEqual(create_proc.returncode, 0, create_proc.stdout + create_proc.stderr)
            pivot_spec = json.dumps(
                {
                    "name": "LIVE_SLICER_PIVOT",
                    "destinationSheet": "PIVOTS",
                    "topLeft": "A3",
                    "sourceSheet": "DATA_RECORDS",
                    "sourceAddress": "A1:C4",
                    "rowFields": ["Region"],
                    "dataFields": [{"name": "Amount", "summary": "sum", "caption": "Total Amount"}],
                }
            )
            slicer_spec = json.dumps(
                {
                    "name": "LIVE_DIRECT_SLICER",
                    "sheet": "PIVOTS",
                    "sourcePivot": "LIVE_SLICER_PIVOT",
                    "sourceField": "Region",
                    "topLeft": "F3",
                    "caption": "Region",
                    "visibleItemsList": ["West"],
                }
            )
            filter_spec = json.dumps({"visibleItemsList": ["East"]})

            pivot_proc = run_skill_cli("pivot", "create", "--workbook-path", str(workbook), "--spec-json", pivot_spec, timeout=300)
            self.assertEqual(pivot_proc.returncode, 0, pivot_proc.stdout + pivot_proc.stderr)

            create_slicer_proc = run_skill_cli("slicer", "create", "--workbook-path", str(workbook), "--spec-json", slicer_spec, timeout=300)
            self.assertEqual(create_slicer_proc.returncode, 0, create_slicer_proc.stdout + create_slicer_proc.stderr)
            self.assertEqual(json.loads(create_slicer_proc.stdout)["slicer"]["name"], "LIVE_DIRECT_SLICER")

            filter_slicer_proc = run_skill_cli(
                "slicer",
                "set-filter",
                "--workbook-path",
                str(workbook),
                "--slicer",
                "LIVE_DIRECT_SLICER",
                "--spec-json",
                filter_spec,
                timeout=300,
            )
            self.assertEqual(filter_slicer_proc.returncode, 0, filter_slicer_proc.stdout + filter_slicer_proc.stderr)
            self.assertTrue(json.loads(filter_slicer_proc.stdout)["changed"])

            clear_slicer_proc = run_skill_cli("slicer", "clear", "--workbook-path", str(workbook), "--slicer", "LIVE_DIRECT_SLICER", timeout=300)
            self.assertEqual(clear_slicer_proc.returncode, 0, clear_slicer_proc.stdout + clear_slicer_proc.stderr)
            self.assertTrue(json.loads(clear_slicer_proc.stdout)["cleared"])

            delete_slicer_proc = run_skill_cli("slicer", "delete", "--workbook-path", str(workbook), "--slicer", "LIVE_DIRECT_SLICER", timeout=300)
            self.assertEqual(delete_slicer_proc.returncode, 0, delete_slicer_proc.stdout + delete_slicer_proc.stderr)
            self.assertTrue(json.loads(delete_slicer_proc.stdout)["deleted"])

    @unittest.skipUnless(LIVE_DESKTOP_MUTATION, "set EXCEL_FOUNDRY_LIVE_DESKTOP=1 and EXCEL_FOUNDRY_LIVE_MUTATION=1 to run live Excel COM mutation tests")
    def test_live_direct_timeline_commands_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-live-timeline-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "direct-timeline.xlsx"
            create_proc = run_pwsh(
                dedent(
                    f"""
                    $excel = New-Object -ComObject Excel.Application
                    $excel.Visible = $false
                    $excel.DisplayAlerts = $false
                    $workbook = $excel.Workbooks.Add()
                    try {{
                        $data = $workbook.Worksheets.Item(1)
                        $data.Name = 'DATA_RECORDS'
                        $data.Range('A1').Value2 = 'OrderDate'
                        $data.Range('B1').Value2 = 'Region'
                        $data.Range('C1').Value2 = 'Amount'
                        $data.Range('A2').Value2 = [datetime]'2026-01-15'
                        $data.Range('B2').Value2 = 'West'
                        $data.Range('C2').Value2 = 10
                        $data.Range('A3').Value2 = [datetime]'2026-02-15'
                        $data.Range('B3').Value2 = 'East'
                        $data.Range('C3').Value2 = 20
                        $data.Range('A4').Value2 = [datetime]'2026-03-15'
                        $data.Range('B4').Value2 = 'West'
                        $data.Range('C4').Value2 = 30
                        $pivot = $workbook.Worksheets.Add()
                        $pivot.Name = 'PIVOTS'
                        $workbook.SaveAs('{workbook}', 51)
                    }}
                    finally {{
                        $workbook.Close($false)
                        $excel.Quit()
                        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($workbook)
                        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
                    }}
                    """
                ),
                timeout=120,
            )
            self.assertEqual(create_proc.returncode, 0, create_proc.stdout + create_proc.stderr)
            pivot_spec = json.dumps(
                {
                    "name": "LIVE_TIMELINE_PIVOT",
                    "destinationSheet": "PIVOTS",
                    "topLeft": "A3",
                    "sourceSheet": "DATA_RECORDS",
                    "sourceAddress": "A1:C4",
                    "rowFields": ["OrderDate"],
                    "dataFields": [{"name": "Amount", "summary": "sum", "caption": "Total Amount"}],
                }
            )
            timeline_spec = json.dumps(
                {
                    "name": "LIVE_DIRECT_TIMELINE",
                    "sheet": "PIVOTS",
                    "sourcePivot": "LIVE_TIMELINE_PIVOT",
                    "sourceField": "OrderDate",
                    "topLeft": "F3",
                    "caption": "Order Date",
                    "timelineLevel": "months",
                    "startDate": "2026-01-01",
                    "endDate": "2026-02-28",
                }
            )
            range_spec = json.dumps(
                {
                    "timelineLevel": "months",
                    "startDate": "2026-02-01",
                    "endDate": "2026-03-31",
                }
            )

            pivot_proc = run_skill_cli("pivot", "create", "--workbook-path", str(workbook), "--spec-json", pivot_spec, timeout=300)
            self.assertEqual(pivot_proc.returncode, 0, pivot_proc.stdout + pivot_proc.stderr)

            create_timeline_proc = run_skill_cli("timeline", "create", "--workbook-path", str(workbook), "--spec-json", timeline_spec, timeout=300)
            self.assertEqual(create_timeline_proc.returncode, 0, create_timeline_proc.stdout + create_timeline_proc.stderr)
            self.assertEqual(json.loads(create_timeline_proc.stdout)["timeline"]["name"], "LIVE_DIRECT_TIMELINE")

            range_timeline_proc = run_skill_cli(
                "timeline",
                "set-range",
                "--workbook-path",
                str(workbook),
                "--timeline",
                "LIVE_DIRECT_TIMELINE",
                "--spec-json",
                range_spec,
                timeout=300,
            )
            self.assertEqual(range_timeline_proc.returncode, 0, range_timeline_proc.stdout + range_timeline_proc.stderr)
            self.assertTrue(json.loads(range_timeline_proc.stdout)["changed"])

            clear_timeline_proc = run_skill_cli("timeline", "clear", "--workbook-path", str(workbook), "--timeline", "LIVE_DIRECT_TIMELINE", timeout=300)
            self.assertEqual(clear_timeline_proc.returncode, 0, clear_timeline_proc.stdout + clear_timeline_proc.stderr)
            self.assertTrue(json.loads(clear_timeline_proc.stdout)["cleared"])

            delete_timeline_proc = run_skill_cli("timeline", "delete", "--workbook-path", str(workbook), "--timeline", "LIVE_DIRECT_TIMELINE", timeout=300)
            self.assertEqual(delete_timeline_proc.returncode, 0, delete_timeline_proc.stdout + delete_timeline_proc.stderr)
            self.assertTrue(json.loads(delete_timeline_proc.stdout)["deleted"])

    @unittest.skipUnless(LIVE_DESKTOP_MUTATION, "set EXCEL_FOUNDRY_LIVE_DESKTOP=1 and EXCEL_FOUNDRY_LIVE_MUTATION=1 to run live Excel COM mutation tests")
    def test_live_workbook_safe_export_writes_pdf_from_temp_copy(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-live-safe-export-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "safe-export-source.xlsx"
            target = tmp / "safe-export-output.pdf"
            create_proc = run_pwsh(
                dedent(
                    f"""
                    $excel = New-Object -ComObject Excel.Application
                    $excel.Visible = $false
                    $excel.DisplayAlerts = $false
                    $workbook = $excel.Workbooks.Add()
                    try {{
                        $sheet = $workbook.Worksheets.Item(1)
                        $sheet.Name = 'Report'
                        $sheet.Range('A1').Value2 = 'Metric'
                        $sheet.Range('B1').Value2 = 'Value'
                        $sheet.Range('A2').Value2 = 'Revenue'
                        $sheet.Range('B2').Value2 = 123
                        $sheet.PageSetup.PrintArea = '$A$1:$B$2'
                        $workbook.SaveAs('{workbook}', 51)
                    }}
                    finally {{
                        $workbook.Close($false)
                        $excel.Quit()
                        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($workbook)
                        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
                    }}
                    """
                ),
                timeout=120,
            )
            self.assertEqual(create_proc.returncode, 0, create_proc.stdout + create_proc.stderr)

            spec = json.dumps({"breakLinks": False, "removeDocumentInfoTypes": [], "runDocumentInspectors": False})
            export_proc = run_skill_cli(
                "workbook",
                "safe-export",
                "--workbook-path",
                str(workbook),
                "--target-path",
                str(target),
                "--spec-json",
                spec,
                timeout=300,
            )
            self.assertEqual(export_proc.returncode, 0, export_proc.stdout + export_proc.stderr)
            payload = json.loads(export_proc.stdout)
            self.assertEqual(payload["targetFormat"], "pdf")
            self.assertEqual(Path(payload["targetPath"]), target.resolve())
            self.assertTrue(target.exists())
            self.assertEqual(target.read_bytes()[:4], b"%PDF")

    @unittest.skipUnless(LIVE_DESKTOP_MUTATION, "set EXCEL_FOUNDRY_LIVE_DESKTOP=1 and EXCEL_FOUNDRY_LIVE_MUTATION=1 to run live Excel COM mutation tests")
    def test_live_what_if_scenario_and_goal_seek_commands_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-live-what-if-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "what-if.xlsx"
            create_proc = run_pwsh(
                dedent(
                    f"""
                    $excel = New-Object -ComObject Excel.Application
                    $excel.Visible = $false
                    $excel.DisplayAlerts = $false
                    $workbook = $excel.Workbooks.Add()
                    try {{
                        $sheet = $workbook.Worksheets.Item(1)
                        $sheet.Name = 'Model'
                        $sheet.Range('A1').Value2 = 'Input'
                        $sheet.Range('B1').Value2 = 'Output'
                        $sheet.Range('A2').Value2 = 10
                        $sheet.Range('B2').Formula = '=A2*2'
                        $workbook.SaveAs('{workbook}', 51)
                    }}
                    finally {{
                        $workbook.Close($false)
                        $excel.Quit()
                        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($workbook)
                        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
                    }}
                    """
                ),
                timeout=120,
            )
            self.assertEqual(create_proc.returncode, 0, create_proc.stdout + create_proc.stderr)

            scenario_spec = json.dumps(
                {
                    "sheet": "Model",
                    "name": "LIVE_DIRECT_SCENARIO",
                    "changingCells": ["A2"],
                    "values": [25],
                    "comment": "live scenario roundtrip",
                }
            )
            set_proc = run_skill_cli("scenario", "set", "--workbook-path", str(workbook), "--spec-json", scenario_spec, timeout=300)
            self.assertEqual(set_proc.returncode, 0, set_proc.stdout + set_proc.stderr)
            set_payload = json.loads(set_proc.stdout)
            self.assertTrue(set_payload["changed"])
            self.assertEqual(set_payload["readback"]["name"], "LIVE_DIRECT_SCENARIO")
            self.assertIn("secretHandling", set_payload)

            list_proc = run_skill_cli("scenario", "list", "--workbook-path", str(workbook), timeout=300)
            self.assertEqual(list_proc.returncode, 0, list_proc.stdout + list_proc.stderr)
            self.assertIn("LIVE_DIRECT_SCENARIO", {item["name"] for item in json.loads(list_proc.stdout)["scenarios"]})

            inspect_proc = run_skill_cli("what-if", "inspect", "--workbook-path", str(workbook), timeout=300)
            self.assertEqual(inspect_proc.returncode, 0, inspect_proc.stdout + inspect_proc.stderr)
            inspect_payload = json.loads(inspect_proc.stdout)
            self.assertGreaterEqual(inspect_payload["inspection"]["counts"]["scenarios"], 1)
            self.assertTrue(any("Solver" in item for item in inspect_payload["limitations"]))

            goal_spec = json.dumps({"sheet": "Model", "formulaCell": "B2", "targetValue": 100, "changingCell": "A2"})
            goal_proc = run_skill_cli("goal-seek", "execute", "--workbook-path", str(workbook), "--spec-json", goal_spec, timeout=300)
            self.assertEqual(goal_proc.returncode, 0, goal_proc.stdout + goal_proc.stderr)
            goal_payload = json.loads(goal_proc.stdout)
            self.assertTrue(goal_payload["goalSeek"]["succeeded"])
            self.assertAlmostEqual(float(goal_payload["readback"]["changingCell"]["value"]), 50.0, places=6)

            delete_proc = run_skill_cli("scenario", "delete", "--workbook-path", str(workbook), "--name", "LIVE_DIRECT_SCENARIO", timeout=300)
            self.assertEqual(delete_proc.returncode, 0, delete_proc.stdout + delete_proc.stderr)
            self.assertTrue(json.loads(delete_proc.stdout)["deleted"])

    @unittest.skipUnless(LIVE_DESKTOP_MUTATION, "set EXCEL_FOUNDRY_LIVE_DESKTOP=1 and EXCEL_FOUNDRY_LIVE_MUTATION=1 to run live Excel COM mutation tests")
    def test_live_formula_audit_inspect_and_export_reports_dependencies(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-live-formula-audit-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "formula-audit.xlsx"
            target = tmp / "formula-audit.json"
            create_proc = run_pwsh(
                dedent(
                    f"""
                    $excel = New-Object -ComObject Excel.Application
                    $excel.Visible = $false
                    $excel.DisplayAlerts = $false
                    $workbook = $excel.Workbooks.Add()
                    try {{
                        $sheet = $workbook.Worksheets.Item(1)
                        $sheet.Name = 'Audit'
                        $sheet.Range('A2').Value2 = 10
                        $sheet.Range('B2').Formula = '=A2*2'
                        $sheet.Range('C2').Formula = '=B2+1'
                        $protected = $workbook.Worksheets.Add()
                        $protected.Name = 'Protected'
                        $protected.Range('A1').Value2 = 1
                        $protected.Range('B1').Formula = '=A1+1'
                        $protected.Protect()
                        $workbook.SaveAs('{workbook}', 51)
                    }}
                    finally {{
                        $workbook.Close($false)
                        $excel.Quit()
                        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($workbook)
                        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
                    }}
                    """
                ),
                timeout=120,
            )
            self.assertEqual(create_proc.returncode, 0, create_proc.stdout + create_proc.stderr)

            inspect_proc = run_skill_cli("formula-audit", "inspect", "--workbook-path", str(workbook), timeout=300)
            self.assertEqual(inspect_proc.returncode, 0, inspect_proc.stdout + inspect_proc.stderr)
            payload = json.loads(inspect_proc.stdout)
            formulas = {item["address"]: item for item in payload["formulas"]}
            self.assertIn("B2", formulas)
            self.assertIn("C2", formulas)
            self.assertIn("A2", " ".join(formulas["B2"]["directPrecedents"]))
            self.assertTrue(any("protected" in warning.lower() for warning in payload["warnings"]))
            self.assertTrue(payload["limitations"])

            export_proc = run_skill_cli(
                "formula-audit",
                "export",
                "--workbook-path",
                str(workbook),
                "--sheet",
                "Audit",
                "--target-path",
                str(target),
                timeout=300,
            )
            self.assertEqual(export_proc.returncode, 0, export_proc.stdout + export_proc.stderr)
            export_payload = json.loads(export_proc.stdout)
            self.assertTrue(export_payload["exported"])
            self.assertEqual(Path(export_payload["targetPath"]), target.resolve())
            self.assertIn("formulas", json.loads(target.read_text(encoding="utf-8")))

    @unittest.skipUnless(LIVE_DESKTOP_MUTATION, "set EXCEL_FOUNDRY_LIVE_DESKTOP=1 and EXCEL_FOUNDRY_LIVE_MUTATION=1 to run live Excel COM mutation tests")
    def test_live_links_and_document_inspect_commands_return_host_limited_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-live-privacy-links-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "privacy-links.xlsx"
            create_proc = run_pwsh(
                dedent(
                    f"""
                    $excel = New-Object -ComObject Excel.Application
                    $excel.Visible = $false
                    $excel.DisplayAlerts = $false
                    $workbook = $excel.Workbooks.Add()
                    try {{
                        $sheet = $workbook.Worksheets.Item(1)
                        $sheet.Name = 'Review'
                        $sheet.Range('A1').Value2 = 'Outbound'
                        $sheet.Hyperlinks.Add($sheet.Range('A2'), 'https://example.invalid/review', '', '', 'Review link') | Out-Null
                        $sheet.Range('B2').AddComment('Review comment') | Out-Null
                        $workbook.SaveAs('{workbook}', 51)
                    }}
                    finally {{
                        $workbook.Close($false)
                        $excel.Quit()
                        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($workbook)
                        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
                    }}
                    """
                ),
                timeout=120,
            )
            self.assertEqual(create_proc.returncode, 0, create_proc.stdout + create_proc.stderr)

            links_proc = run_skill_cli("workbook", "links", "--workbook-path", str(workbook), timeout=300)
            self.assertEqual(links_proc.returncode, 0, links_proc.stdout + links_proc.stderr)
            links_payload = json.loads(links_proc.stdout)
            self.assertEqual(links_payload["backend"], "excel")
            self.assertIsInstance(links_payload["links"], list)

            inspect_proc = run_skill_cli("workbook", "document-inspect", "--workbook-path", str(workbook), timeout=300)
            self.assertEqual(inspect_proc.returncode, 0, inspect_proc.stdout + inspect_proc.stderr)
            inspection = json.loads(inspect_proc.stdout)["inspection"]
            manual_messages = " ".join(item["message"] for item in inspection["manualFindings"])
            self.assertIn("comment", manual_messages.lower())
            self.assertIn("hyperlink", manual_messages.lower())

    @unittest.skipUnless(LIVE_DESKTOP_MUTATION, "set EXCEL_FOUNDRY_LIVE_DESKTOP=1 and EXCEL_FOUNDRY_LIVE_MUTATION=1 to run live Excel COM mutation tests")
    def test_live_direct_shape_picture_and_control_commands_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory(prefix="excel-foundry-live-visuals-") as tmpdir:
            tmp = Path(tmpdir)
            workbook = tmp / "direct-visuals.xlsx"
            create_proc = run_pwsh(
                dedent(
                    f"""
                    $excel = New-Object -ComObject Excel.Application
                    $excel.Visible = $false
                    $excel.DisplayAlerts = $false
                    $workbook = $excel.Workbooks.Add()
                    try {{
                        $sheet = $workbook.Worksheets.Item(1)
                        $sheet.Name = 'DATA_RECORDS'
                        $sheet.Range('A1').Value2 = 'Code'
                        $sheet.Range('B1').Value2 = 'Amount'
                        $sheet.Range('A2').Value2 = 'A100'
                        $sheet.Range('B2').Value2 = 10
                        $workbook.SaveAs('{workbook}', 51)
                    }}
                    finally {{
                        $workbook.Close($false)
                        $excel.Quit()
                        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($workbook)
                        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
                    }}
                    """
                ),
                timeout=120,
            )
            self.assertEqual(create_proc.returncode, 0, create_proc.stdout + create_proc.stderr)
            image_path = tmp / "pixel.png"
            image_path.write_bytes(
                base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/lZQtWQAAAABJRU5ErkJggg=="
                )
            )
            shape_spec = json.dumps(
                {
                    "sheet": "DATA_RECORDS",
                    "name": "LIVE_DIRECT_SHAPE",
                    "topLeft": "L2",
                    "width": 120,
                    "height": 40,
                    "text": "Live shape",
                    "altText": "live shape alt text",
                    "fillColor": "#4472C4",
                }
            )
            shape_update_spec = json.dumps(
                {
                    "name": "LIVE_DIRECT_SHAPE",
                    "text": "Updated shape",
                    "altText": "updated shape alt text",
                    "width": 132,
                }
            )
            picture_spec = json.dumps(
                {
                    "sheet": "DATA_RECORDS",
                    "name": "LIVE_DIRECT_PICTURE",
                    "sourcePath": str(image_path),
                    "topLeft": "L8",
                    "width": 40,
                    "height": 40,
                    "altText": "live picture alt text",
                }
            )

            create_shape_proc = run_skill_cli("shape", "create", "--workbook-path", str(workbook), "--spec-json", shape_spec, timeout=300)
            self.assertEqual(create_shape_proc.returncode, 0, create_shape_proc.stdout + create_shape_proc.stderr)
            self.assertEqual(json.loads(create_shape_proc.stdout)["shape"]["name"], "LIVE_DIRECT_SHAPE")

            update_shape_proc = run_skill_cli("shape", "update", "--workbook-path", str(workbook), "--spec-json", shape_update_spec, timeout=300)
            self.assertEqual(update_shape_proc.returncode, 0, update_shape_proc.stdout + update_shape_proc.stderr)
            self.assertEqual(json.loads(update_shape_proc.stdout)["shape"]["text"], "Updated shape")

            add_picture_proc = run_skill_cli("picture", "add", "--workbook-path", str(workbook), "--spec-json", picture_spec, timeout=300)
            self.assertEqual(add_picture_proc.returncode, 0, add_picture_proc.stdout + add_picture_proc.stderr)
            self.assertEqual(json.loads(add_picture_proc.stdout)["picture"]["category"], "picture")

            control_list_proc = run_skill_cli("control", "list", "--workbook-path", str(workbook), timeout=300)
            self.assertEqual(control_list_proc.returncode, 0, control_list_proc.stdout + control_list_proc.stderr)
            self.assertIsInstance(json.loads(control_list_proc.stdout)["controls"], list)

            delete_picture_proc = run_skill_cli("picture", "delete", "--workbook-path", str(workbook), "--name", "LIVE_DIRECT_PICTURE", timeout=300)
            self.assertEqual(delete_picture_proc.returncode, 0, delete_picture_proc.stdout + delete_picture_proc.stderr)
            self.assertTrue(json.loads(delete_picture_proc.stdout)["deleted"])

            delete_shape_proc = run_skill_cli("shape", "delete", "--workbook-path", str(workbook), "--name", "LIVE_DIRECT_SHAPE", timeout=300)
            self.assertEqual(delete_shape_proc.returncode, 0, delete_shape_proc.stdout + delete_shape_proc.stderr)
            self.assertTrue(json.loads(delete_shape_proc.stdout)["deleted"])

    @unittest.skipUnless(LIVE_DESKTOP_MUTATION, "set EXCEL_FOUNDRY_LIVE_DESKTOP=1 and EXCEL_FOUNDRY_LIVE_MUTATION=1 to run live Excel COM mutation tests")
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

    @unittest.skipUnless(LIVE_DESKTOP_MUTATION, "set EXCEL_FOUNDRY_LIVE_DESKTOP=1 and EXCEL_FOUNDRY_LIVE_MUTATION=1 to run live Excel COM mutation tests")
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
