from __future__ import annotations

import atexit
import base64
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from textwrap import dedent
import xml.etree.ElementTree as ET


WORKBOOK_FILENAME = "generated-test-workbook.xlsm"
MANIFEST_FILENAME = "excel-foundry.manifest.json"
SHEET_PRIMARY = "Inputs"
SHEET_SECONDARY = "Staging"
TABLE_PRIMARY = "TableInputs"
TABLE_SECONDARY = "TableLines"
NAME_PRIMARY = "AnchorValue"
QUERY_PRIMARY = "QueryInputs"
QUERY_SECONDARY = "QueryLines"
QUERY_MATCHED = "QueryMatched"
QUERY_UNMATCHED = "QueryUnmatched"
CONNECTION_PRIMARY = f"Query - {QUERY_PRIMARY}"
MODULE_PRIMARY = "ModuleMain"
MODULE_SECONDARY = "ModuleExport"
SHEET_MODULE = SHEET_SECONDARY
PACKAGE_NS = "http://schemas.openxmlformats.org/package/2006/content-types"


def _excel_com_is_available() -> bool:
    if os.name != "nt":
        return False
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        return False
    proc = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-Command",
            dedent(
                """
                try {
                    $excel = New-Object -ComObject Excel.Application
                    try { 'yes' } finally { $excel.Quit() | Out-Null }
                }
                catch {
                    'no'
                }
                """
            ),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=60,
    )
    return proc.returncode == 0 and proc.stdout.strip() == "yes"


@dataclass(frozen=True)
class GeneratedFixtureWorkspace:
    tempdir: tempfile.TemporaryDirectory[str]
    root: Path
    workbook_path: Path
    manifest_path: Path
    tables_path: Path
    names_path: Path
    conditional_formatting_path: Path
    vba_project_path: Path
    vba_references_path: Path
    queries_dir: Path
    queries_path: Path
    connections_path: Path
    model_path: Path
    refresh_path: Path
    module_primary_path: Path
    module_secondary_path: Path
    sheet_module_path: Path
    primary_query_file: Path


def _build_data_mashup_base64() -> str:
    mashup_buffer = BytesIO()
    with zipfile.ZipFile(mashup_buffer, "w", compression=zipfile.ZIP_DEFLATED) as mashup_zip:
        mashup_zip.writestr(
            "[Content_Types].xml",
            "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'/>",
        )
        mashup_zip.writestr(
            "Formulas/Section1.m",
            dedent(
                f"""\
                section Section1;
                shared {QUERY_MATCHED} =
                let
                    Source = #table({{"Code","Amount"}}, {{"A-100", 10}})
                in
                    Source;
                shared {QUERY_UNMATCHED} =
                let
                    Source = #table({{"Code","Amount"}}, {{"B-200", 20}})
                in
                    Source;
                shared {QUERY_PRIMARY} =
                let
                    Source = #table({{"Code","Amount"}}, {{"C-300", 30}})
                in
                    Source;
                shared {QUERY_SECONDARY} =
                let
                    Source = #table({{"Code","LineAmount"}}, {{"C-300", 30}})
                in
                    Source;
                """
            ),
        )
    return base64.b64encode(mashup_buffer.getvalue()).decode("ascii")


def _build_excel_backed_workbook(workbook_path: Path) -> None:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        raise RuntimeError("PowerShell is unavailable for Excel-backed fixture generation.")

    script = dedent(
        f"""
        $excel = $null
        $workbook = $null
        $sheet1 = $null
        $sheet2 = $null
        $table1 = $null
        $table2 = $null
        try {{
            $excel = New-Object -ComObject Excel.Application
            $excel.Visible = $false
            $excel.DisplayAlerts = $false
            $workbook = $excel.Workbooks.Add()
            while ($workbook.Worksheets.Count -lt 2) {{
                $null = $workbook.Worksheets.Add()
            }}

            $sheet1 = $workbook.Worksheets.Item(1)
            $sheet2 = $workbook.Worksheets.Item(2)
            $sheet1.Name = '{SHEET_PRIMARY}'
            $sheet2.Name = '{SHEET_SECONDARY}'

            $sheet1.Range('A1').Value2 = 'Code'
            $sheet1.Range('B1').Value2 = 'Amount'
            $sheet1.Range('A2').Value2 = 'A-100'
            $sheet1.Range('B2').Value2 = 10
            $sheet1.Range('A3').Value2 = 'B-200'
            $sheet1.Range('B3').Value2 = 20

            $sheet2.Range('A1').Value2 = 'Code'
            $sheet2.Range('B1').Value2 = 'LineAmount'
            $sheet2.Range('A2').Value2 = 'A-100'
            $sheet2.Range('B2').Value2 = 10
            $sheet2.Range('A3').Value2 = 'B-200'
            $sheet2.Range('B3').Value2 = 20

            $table1 = $sheet1.ListObjects.Add(1, $sheet1.Range('A1:B3'), $null, 1)
            $table1.Name = '{TABLE_PRIMARY}'
            $table2 = $sheet2.ListObjects.Add(1, $sheet2.Range('A1:B3'), $null, 1)
            $table2.Name = '{TABLE_SECONDARY}'

            $null = $workbook.Names.Add('{NAME_PRIMARY}', '=Inputs!$B$2')
            $sheet1.Range('B2').AddComment('Generated review note')
            $sheet1.Hyperlinks.Add($sheet1.Range('A2'), 'https://example.invalid/{QUERY_PRIMARY}', '', '', 'Source')
            $sheet1.PageSetup.PrintTitleRows = '$1:$1'
            $sheet1.PageSetup.Orientation = 2

            $workbook.SaveAs('{workbook_path}', 52)
        }}
        finally {{
            foreach ($obj in @($table2, $table1, $sheet2, $sheet1, $workbook)) {{
                if ($null -ne $obj) {{
                    try {{ $obj | Out-Null }} catch {{}}
                    try {{ [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($obj) }} catch {{}}
                }}
            }}
            if ($null -ne $excel) {{
                try {{ $excel.Quit() | Out-Null }} catch {{}}
                try {{ [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) }} catch {{}}
            }}
            [gc]::Collect()
            [gc]::WaitForPendingFinalizers()
        }}
        """
    )

    proc = subprocess.run(
        [shell, "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout + proc.stderr)


def _inject_package_parts(workbook_path: Path) -> None:
    mashup_base64 = _build_data_mashup_base64()
    connections_xml = dedent(
        f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <connections xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <connection id="1" name="Query - {QUERY_MATCHED}" description="Matched query" type="1" background="1"><dbPr connection="Provider=Microsoft.Mashup.OleDb.1;" command="SELECT * FROM [{QUERY_MATCHED}]"/></connection>
          <connection id="2" name="Query - {QUERY_UNMATCHED}" description="Unmatched query" type="1" background="1"><dbPr connection="Provider=Microsoft.Mashup.OleDb.1;" command="SELECT * FROM [{QUERY_UNMATCHED}]"/></connection>
          <connection id="3" name="{CONNECTION_PRIMARY}" description="Inputs query" type="1" background="1"><dbPr connection="Provider=Microsoft.Mashup.OleDb.1;" command="SELECT * FROM [{QUERY_PRIMARY}]"/></connection>
          <connection id="4" name="Query - {QUERY_SECONDARY}" description="Lines query" type="1" background="1"><dbPr connection="Provider=Microsoft.Mashup.OleDb.1;" command="SELECT * FROM [{QUERY_SECONDARY}]"/></connection>
        </connections>
        """
    )
    mashup_xml = (
        f'<?xml version="1.0" encoding="utf-8"?><DataMashup xmlns="http://schemas.microsoft.com/DataMashup">{mashup_base64}</DataMashup>'
    )

    with zipfile.ZipFile(workbook_path, "r") as existing_zip:
        current_entries = {name: existing_zip.read(name) for name in existing_zip.namelist()}

    content_types_root = ET.fromstring(current_entries["[Content_Types].xml"])
    override_qname = f"{{{PACKAGE_NS}}}Override"
    required_overrides = {
        "/xl/connections.xml": "application/vnd.openxmlformats-officedocument.spreadsheetml.connections+xml",
        "/customXml/item1.xml": "application/xml",
        "/xl/vbaProject.bin": "application/vnd.ms-office.vbaProject",
    }
    existing_part_names = {
        node.attrib.get("PartName"): node for node in content_types_root.findall(override_qname)
    }
    for part_name, content_type in required_overrides.items():
        if part_name not in existing_part_names:
            ET.SubElement(
                content_types_root,
                override_qname,
                {"PartName": part_name, "ContentType": content_type},
            )
    current_entries["[Content_Types].xml"] = ET.tostring(content_types_root, encoding="utf-8", xml_declaration=True)
    current_entries["xl/connections.xml"] = connections_xml.encode("utf-8")
    current_entries["customXml/item1.xml"] = mashup_xml.encode("utf-8")
    current_entries["xl/vbaProject.bin"] = b"excel-foundry-generated-vba-placeholder"

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as updated_zip:
        for name, content in current_entries.items():
            updated_zip.writestr(name, content)
    workbook_path.write_bytes(buffer.getvalue())


def build_generated_workbook(workbook_path: Path) -> None:
    mashup_base64 = _build_data_mashup_base64()
    workbook_files: dict[str, bytes | str] = {
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
            f"""\
            <?xml version="1.0" encoding="UTF-8"?>
            <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <sheets>
                <sheet name="{SHEET_PRIMARY}" sheetId="1" r:id="rId1"/>
                <sheet name="{SHEET_SECONDARY}" sheetId="2" r:id="rId2"/>
              </sheets>
              <definedNames>
                <definedName name="{NAME_PRIMARY}">{SHEET_PRIMARY}!$B$2</definedName>
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
            f"""\
            <?xml version="1.0" encoding="UTF-8"?>
            <table xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" id="1" name="{TABLE_PRIMARY}" displayName="{TABLE_PRIMARY}" ref="A1:B2" totalsRowShown="0">
              <autoFilter ref="A1:B2"/>
              <tableColumns count="2">
                <tableColumn id="1" name="Code"/>
                <tableColumn id="2" name="Amount"/>
              </tableColumns>
            </table>
            """
        ),
        "xl/tables/table2.xml": dedent(
            f"""\
            <?xml version="1.0" encoding="UTF-8"?>
            <table xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" id="2" name="{TABLE_SECONDARY}" displayName="{TABLE_SECONDARY}" ref="A1:B2" totalsRowShown="0">
              <autoFilter ref="A1:B2"/>
              <tableColumns count="2">
                <tableColumn id="1" name="Code"/>
                <tableColumn id="2" name="LineAmount"/>
              </tableColumns>
            </table>
            """
        ),
        "xl/connections.xml": dedent(
            f"""\
            <?xml version="1.0" encoding="UTF-8"?>
            <connections xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <connection id="1" name="Query - {QUERY_MATCHED}" description="Matched query" type="1" background="1"><dbPr connection="Provider=Microsoft.Mashup.OleDb.1;" command="SELECT * FROM [{QUERY_MATCHED}]"/></connection>
              <connection id="2" name="Query - {QUERY_UNMATCHED}" description="Unmatched query" type="1" background="1"><dbPr connection="Provider=Microsoft.Mashup.OleDb.1;" command="SELECT * FROM [{QUERY_UNMATCHED}]"/></connection>
              <connection id="3" name="{CONNECTION_PRIMARY}" description="Inputs query" type="1" background="1"><dbPr connection="Provider=Microsoft.Mashup.OleDb.1;" command="SELECT * FROM [{QUERY_PRIMARY}]"/></connection>
              <connection id="4" name="Query - {QUERY_SECONDARY}" description="Lines query" type="1" background="1"><dbPr connection="Provider=Microsoft.Mashup.OleDb.1;" command="SELECT * FROM [{QUERY_SECONDARY}]"/></connection>
            </connections>
            """
        ),
        "xl/sharedStrings.xml": dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="5" uniqueCount="5">
              <si><t>Code</t></si>
              <si><t>Amount</t></si>
              <si><t>A-100</t></si>
              <si><t>Code</t></si>
              <si><t>LineAmount</t></si>
            </sst>
            """
        ),
        "customXml/item1.xml": (
            f'<?xml version="1.0" encoding="utf-8"?><DataMashup xmlns="http://schemas.microsoft.com/DataMashup">{mashup_base64}</DataMashup>'
        ),
        "xl/vbaProject.bin": b"generated-vba-project",
    }

    with zipfile.ZipFile(workbook_path, "w", compression=zipfile.ZIP_DEFLATED) as workbook_zip:
        for name, content in workbook_files.items():
            workbook_zip.writestr(name, content)


def create_generated_fixture_workspace() -> GeneratedFixtureWorkspace:
    tempdir = tempfile.TemporaryDirectory(prefix="excel-foundry-generated-fixture-")
    root = Path(tempdir.name)
    workbook_path = root / WORKBOOK_FILENAME
    manifest_path = root / MANIFEST_FILENAME
    workbook_structure = root / "workbook_structure"
    power_query = root / "power_query"
    queries_dir = power_query / "queries"
    macros_modules = root / "macros" / "modules"
    macros_sheets = root / "macros" / "sheets"

    workbook_structure.mkdir(parents=True, exist_ok=True)
    queries_dir.mkdir(parents=True, exist_ok=True)
    macros_modules.mkdir(parents=True, exist_ok=True)
    macros_sheets.mkdir(parents=True, exist_ok=True)

    if _excel_com_is_available():
        _build_excel_backed_workbook(workbook_path)
        _inject_package_parts(workbook_path)
    else:
        build_generated_workbook(workbook_path)

    module_primary_path = macros_modules / f"{MODULE_PRIMARY}.vba"
    module_secondary_path = macros_modules / f"{MODULE_SECONDARY}.vba"
    sheet_module_path = macros_sheets / f"{SHEET_MODULE}.vba"
    module_primary_path.write_text(
        dedent(
            """\
            Attribute VB_Name = "ModuleMain"
            Option Explicit

            Public Sub RunGeneratedSync()
                MsgBox "Generated sync"
            End Sub
            """
        ),
        encoding="utf-8",
    )
    module_secondary_path.write_text(
        dedent(
            """\
            Attribute VB_Name = "ModuleExport"
            Option Explicit

            Public Sub ExportGeneratedCsv()
                Debug.Print "export"
            End Sub
            """
        ),
        encoding="utf-8",
    )
    sheet_module_path.write_text(
        dedent(
            f"""\
            Attribute VB_Name = "{SHEET_MODULE}"
            Option Explicit

            Private Sub Worksheet_Activate()
                Debug.Print "{SHEET_MODULE}"
            End Sub
            """
        ),
        encoding="utf-8",
    )

    primary_query_file = queries_dir / f"{QUERY_MATCHED}.pq"
    primary_query_file.write_text(
        "let\n    Source = #table({\"Code\",\"Amount\"}, {{\"A-100\", 10}})\nin\n    Source\n",
        encoding="utf-8",
    )
    (queries_dir / f"{QUERY_UNMATCHED}.pq").write_text(
        "let\n    Source = #table({\"Code\",\"Amount\"}, {{\"B-200\", 20}})\nin\n    Source\n",
        encoding="utf-8",
    )
    (queries_dir / f"{QUERY_PRIMARY}.pq").write_text(
        "let\n    Source = #table({\"Code\",\"Amount\"}, {{\"C-300\", 30}})\nin\n    Source\n",
        encoding="utf-8",
    )
    (queries_dir / f"{QUERY_SECONDARY}.pq").write_text(
        "let\n    Source = #table({\"Code\",\"LineAmount\"}, {{\"C-300\", 30}})\nin\n    Source\n",
        encoding="utf-8",
    )

    tables_path = workbook_structure / "defaults_tables.json"
    tables_path.write_text(
        json.dumps(
            {
                "tables": [
                    {"sheet": SHEET_PRIMARY, "name": TABLE_PRIMARY, "topLeft": "A1", "headers": ["Code", "Amount"]},
                    {"sheet": SHEET_SECONDARY, "name": TABLE_SECONDARY, "topLeft": "A1", "headers": ["Code", "LineAmount"]},
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    names_path = workbook_structure / "names.json"
    names_path.write_text(
        json.dumps({"names": [{"name": NAME_PRIMARY, "refersTo": f"={SHEET_PRIMARY}!$B$2", "scope": "workbook"}]}, indent=2)
        + "\n",
        encoding="utf-8",
    )

    conditional_formatting_path = workbook_structure / "conditional_formatting.json"
    conditional_formatting_path.write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "id": "CF-GENERATED-0001",
                        "sheet": SHEET_PRIMARY,
                        "address": "$B$2:$B$10",
                        "formula": "=$B2>0",
                        "priority": 1,
                        "stopIfTrue": False,
                        "format": {"interiorColor": "#FFF2CC", "fontColor": "#000000", "bold": False},
                    }
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    vba_project_path = workbook_structure / "vba_project.json"
    vba_project_path.write_text(
        json.dumps(
            {
                "accessible": False,
                "components": [
                    {"name": MODULE_PRIMARY, "type": "standard-module"},
                    {"name": MODULE_SECONDARY, "type": "standard-module"},
                    {"name": SHEET_MODULE, "type": "worksheet-module"},
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    vba_references_path = workbook_structure / "vba_references.json"
    vba_references_path.write_text(json.dumps({"references": []}, indent=2) + "\n", encoding="utf-8")

    queries_path = power_query / "queries.json"
    queries_path.write_text(
        json.dumps(
            {
                "queries": [
                    {"name": QUERY_MATCHED, "connectionName": f"Query - {QUERY_MATCHED}"},
                    {"name": QUERY_UNMATCHED, "connectionName": f"Query - {QUERY_UNMATCHED}"},
                    {"name": QUERY_PRIMARY, "connectionName": CONNECTION_PRIMARY},
                    {"name": QUERY_SECONDARY, "connectionName": f"Query - {QUERY_SECONDARY}"},
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    connections_path = power_query / "connections.json"
    connections_path.write_text(
        json.dumps(
            {
                "connections": [
                    {"name": f"Query - {QUERY_MATCHED}"},
                    {"name": f"Query - {QUERY_UNMATCHED}"},
                    {"name": CONNECTION_PRIMARY},
                    {"name": f"Query - {QUERY_SECONDARY}"},
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    model_path = power_query / "model.json"
    model_path.write_text(json.dumps({"modelTables": []}, indent=2) + "\n", encoding="utf-8")

    refresh_path = power_query / "refresh.json"
    refresh_path.write_text(
        json.dumps(
            {
                "queries": [
                    {"name": QUERY_MATCHED, "connectionName": f"Query - {QUERY_MATCHED}"},
                    {"name": QUERY_UNMATCHED, "connectionName": f"Query - {QUERY_UNMATCHED}"},
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    manifest_path.write_text(
        json.dumps(
            {
                "workbookPath": WORKBOOK_FILENAME,
                "vbaComponents": [
                    {"name": MODULE_PRIMARY, "path": f"macros/modules/{MODULE_PRIMARY}.vba"},
                    {"name": MODULE_SECONDARY, "path": f"macros/modules/{MODULE_SECONDARY}.vba"},
                    {"name": SHEET_MODULE, "path": f"macros/sheets/{SHEET_MODULE}.vba"},
                ],
                "vbaProject": {
                    "projectPath": "workbook_structure/vba_project.json",
                    "referencesPath": "workbook_structure/vba_references.json",
                },
                "powerQuery": {
                    "queriesDirectory": "power_query/queries",
                    "queriesPath": "power_query/queries.json",
                    "connectionsPath": "power_query/connections.json",
                    "modelPath": "power_query/model.json",
                    "refreshPath": "power_query/refresh.json",
                },
                "structure": {
                    "tablesPath": "workbook_structure/defaults_tables.json",
                    "namesPath": "workbook_structure/names.json",
                    "conditionalFormattingPath": "workbook_structure/conditional_formatting.json",
                    "tablesDiscovery": {"mode": "all"},
                    "namesDiscovery": {"mode": "all", "excludeBuiltIn": True},
                    "conditionalFormattingDiscovery": {"mode": "all-major"},
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return GeneratedFixtureWorkspace(
        tempdir=tempdir,
        root=root,
        workbook_path=workbook_path,
        manifest_path=manifest_path,
        tables_path=tables_path,
        names_path=names_path,
        conditional_formatting_path=conditional_formatting_path,
        vba_project_path=vba_project_path,
        vba_references_path=vba_references_path,
        queries_dir=queries_dir,
        queries_path=queries_path,
        connections_path=connections_path,
        model_path=model_path,
        refresh_path=refresh_path,
        module_primary_path=module_primary_path,
        module_secondary_path=module_secondary_path,
        sheet_module_path=sheet_module_path,
        primary_query_file=primary_query_file,
    )


_WORKSPACE = create_generated_fixture_workspace()
atexit.register(_WORKSPACE.tempdir.cleanup)


def get_generated_fixture_workspace() -> GeneratedFixtureWorkspace:
    return _WORKSPACE
