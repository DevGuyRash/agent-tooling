#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
CELL_RE = re.compile(r"^([A-Z]+)(\d+)$")
INTERNAL_NAME_PREFIXES = ("_xlfn.", "_xlpm.", "_xlws.")


def qn(namespace: str, name: str) -> str:
    return f"{{{NS[namespace]}}}{name}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def normalize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize_json(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [normalize_json(item) for item in value]
    return value


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(normalize_json(payload), indent=2) + "\n", encoding="utf-8")


def col_to_index(label: str) -> int:
    value = 0
    for char in label:
        value = (value * 26) + (ord(char.upper()) - ord("A") + 1)
    return value


def index_to_col(index: int) -> str:
    result = []
    value = index
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        result.append(chr(ord("A") + remainder))
    return "".join(reversed(result))


def split_cell_ref(cell_ref: str) -> tuple[int, int]:
    match = CELL_RE.match(cell_ref.upper())
    if not match:
        raise ValueError(f"unsupported cell ref: {cell_ref}")
    return int(match.group(2)), col_to_index(match.group(1))


def parse_range(range_ref: str) -> tuple[int, int, int, int]:
    start, end = range_ref.split(":")
    start_row, start_col = split_cell_ref(start)
    end_row, end_col = split_cell_ref(end)
    return start_row, start_col, end_row, end_col


def address(row: int, col: int) -> str:
    return f"{index_to_col(col)}{row}"


def rel_target(base: str, target: str) -> str:
    parent = Path(base).parent.as_posix()
    combined = f"{parent}/{target}"
    parts: list[str] = []
    for part in combined.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "workbook"


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-") or "item"


def normalize_color(attributes: dict[str, str]) -> str | None:
    rgb = attributes.get("rgb")
    if rgb:
        rgb = rgb.upper()
        if len(rgb) == 8:
            rgb = rgb[2:]
        return f"#{rgb}"
    return None


class WorkbookPackage:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.zip = zipfile.ZipFile(path)
        self.shared_strings = self._load_shared_strings()
        self.dxfs = self._load_dxfs()
        self.workbook_tree = self._xml("xl/workbook.xml")
        self.workbook_rels = self._rels("xl/_rels/workbook.xml.rels")
        self.sheet_names_by_path: dict[str, str] = {}
        self.sheet_ids_by_path: dict[str, str] = {}
        for sheet in self.workbook_tree.findall("./main:sheets/main:sheet", NS):
            rid = sheet.attrib.get(f"{{{NS['rel']}}}id", "")
            target = self.workbook_rels.get(rid)
            if not target:
                continue
            path_key = rel_target("xl/workbook.xml", target)
            self.sheet_names_by_path[path_key] = sheet.attrib.get("name", path_key)
            self.sheet_ids_by_path[path_key] = sheet.attrib.get("sheetId", "")

    def close(self) -> None:
        self.zip.close()

    def names(self) -> list[str]:
        return self.zip.namelist()

    def exists(self, part: str) -> bool:
        try:
            self.zip.getinfo(part)
            return True
        except KeyError:
            return False

    def read_bytes(self, part: str) -> bytes:
        return self.zip.read(part)

    def _xml(self, part: str) -> ET.Element:
        return ET.fromstring(self.read_bytes(part))

    def _rels(self, part: str) -> dict[str, str]:
        if not self.exists(part):
            return {}
        root = ET.fromstring(self.read_bytes(part))
        rels = {}
        for rel in root.findall(f"./{{{REL_NS}}}Relationship"):
            rels[rel.attrib["Id"]] = rel.attrib["Target"]
        return rels

    def _load_shared_strings(self) -> list[str]:
        if not self.exists("xl/sharedStrings.xml"):
            return []
        root = self._xml("xl/sharedStrings.xml")
        values = []
        for item in root.findall("./main:si", NS):
            values.append("".join(node.text or "" for node in item.findall(".//main:t", NS)))
        return values

    def _load_dxfs(self) -> list[dict[str, Any]]:
        if not self.exists("xl/styles.xml"):
            return []
        root = self._xml("xl/styles.xml")
        dxfs = []
        for dxf in root.findall("./main:dxfs/main:dxf", NS):
            fill = dxf.find("./main:fill/main:patternFill/main:fgColor", NS)
            font = dxf.find("./main:font", NS)
            font_color = None
            bold = False
            if font is not None:
                bold = font.find("./main:b", NS) is not None
                color_node = font.find("./main:color", NS)
                if color_node is not None:
                    font_color = normalize_color(color_node.attrib)
            dxfs.append(
                {
                    "interiorColor": normalize_color(fill.attrib) if fill is not None else None,
                    "fontColor": font_color,
                    "bold": bold,
                }
            )
        return dxfs


def decode_cell_value(cell: ET.Element, shared_strings: list[str]) -> Any:
    cell_type = cell.attrib.get("t")
    value_node = cell.find("./main:v", NS)
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//main:t", NS))
    if value_node is None:
        formula = cell.find("./main:f", NS)
        return f"={formula.text}" if formula is not None and formula.text else None
    raw = value_node.text or ""
    if cell_type == "s":
        try:
            return shared_strings[int(raw)]
        except (ValueError, IndexError):
            return raw
    if cell_type == "b":
        return raw == "1"
    if cell_type == "str":
        return raw
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"-?\d+\.\d+", raw):
        return float(raw)
    return raw


def extract_sheet_cells(package: WorkbookPackage, part: str) -> dict[str, Any]:
    root = package._xml(part)
    values: dict[str, Any] = {}
    for cell in root.findall(".//main:sheetData/main:row/main:c", NS):
        ref = cell.attrib.get("r")
        if ref:
            values[ref] = decode_cell_value(cell, package.shared_strings)
    return values


def extract_table_rows(cells: dict[str, Any], table_ref: str) -> list[list[Any]]:
    start_row, start_col, end_row, end_col = parse_range(table_ref)
    rows = []
    for row in range(start_row + 1, end_row + 1):
        rows.append([cells.get(address(row, col)) for col in range(start_col, end_col + 1)])
    while rows and all(value is None for value in rows[-1]):
        rows.pop()
    return rows


def parse_mashup_package(payload: bytes) -> dict[str, bytes]:
    start = payload.find(b"PK")
    if start < 0:
        return {}
    entries: dict[str, bytes] = {}
    cursor = start
    while cursor + 30 <= len(payload):
        if payload[cursor : cursor + 4] != b"PK\x03\x04":
            next_cursor = payload.find(b"PK\x03\x04", cursor + 1)
            if next_cursor < 0:
                break
            cursor = next_cursor
            continue
        (
            _version,
            flags,
            compression,
            _mtime,
            _mdate,
            _crc32,
            compressed_size,
            _uncompressed_size,
            name_length,
            extra_length,
        ) = struct.unpack("<HHHHHIIIHH", payload[cursor + 4 : cursor + 30])
        name_start = cursor + 30
        name_end = name_start + name_length
        extra_end = name_end + extra_length
        name = payload[name_start:name_end].decode("utf-8", errors="replace")
        data_start = extra_end
        data_end = data_start + compressed_size
        if data_end > len(payload):
            break
        raw_data = payload[data_start:data_end]
        if compression == 0:
            data = raw_data
        elif compression == 8:
            import zlib

            data = zlib.decompress(raw_data, -15)
        else:
            data = raw_data
        entries[name] = data
        cursor = data_end
        if flags & 0x8:
            if payload[cursor : cursor + 4] == b"PK\x07\x08":
                cursor += 16
            else:
                cursor += 12
    return entries


def extract_query_blocks(formula_text: str) -> list[dict[str, Any]]:
    pattern = re.compile(r"shared\s+([A-Za-z0-9_]+)\s*=\s*(.*?);(?=\s*shared\s+[A-Za-z0-9_]+\s*=|\s*$)", re.S)
    queries = []
    for name, body in pattern.findall(formula_text):
        queries.append(
            {
                "name": name,
                "description": "",
                "formula": body.strip(),
                "source": "data-mashup",
            }
        )
    return queries


def extract_data_mashup(package: WorkbookPackage) -> dict[str, Any]:
    candidates = [name for name in package.names() if name.startswith("customXml/item") and name.endswith(".xml")]
    for candidate in candidates:
        raw = package.read_bytes(candidate)
        for encoding in ("utf-16", "utf-8"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                text = ""
        if "<DataMashup" not in text:
            continue
        match = re.search(r"<DataMashup[^>]*>([^<]+)</DataMashup>", text)
        if not match:
            continue
        payload = base64.b64decode(match.group(1))
        entries = parse_mashup_package(payload)
        queries = []
        for name, entry in entries.items():
            if name.startswith("Formulas/") and name.endswith(".m"):
                try:
                    formula_text = entry.decode("utf-8")
                except UnicodeDecodeError:
                    formula_text = entry.decode("latin-1", errors="replace")
                queries.extend(extract_query_blocks(formula_text))
        return {
            "present": True,
            "candidate": candidate,
            "sha256": sha256_bytes(payload),
            "entries": sorted(entries),
            "queries": queries,
        }
    return {"present": False}


def extract_ooxml(workbook_path: Path) -> dict[str, Any]:
    package = WorkbookPackage(workbook_path)
    try:
        workbook_tree = package.workbook_tree
        names = [
            {
                "name": item.attrib.get("name", ""),
                "localSheetId": item.attrib.get("localSheetId"),
                "hidden": item.attrib.get("hidden") == "1",
                "refersTo": item.text or "",
            }
            for item in workbook_tree.findall("./main:definedNames/main:definedName", NS)
        ]
        sheets: list[dict[str, Any]] = []
        tables: list[dict[str, Any]] = []
        mappings: list[dict[str, Any]] = []
        conditional_rules: list[dict[str, Any]] = []

        for sheet_part, sheet_name in package.sheet_names_by_path.items():
            sheet_tree = package._xml(sheet_part)
            sheet_cells = extract_sheet_cells(package, sheet_part)
            rel_part = str(Path(sheet_part).parent / "_rels" / f"{Path(sheet_part).name}.rels").replace("\\", "/")
            rels = package._rels(rel_part)
            sheet_tables = []
            for table_part in sheet_tree.findall("./main:tableParts/main:tablePart", NS):
                rid = table_part.attrib.get(f"{{{NS['rel']}}}id", "")
                target = rels.get(rid)
                if not target:
                    continue
                table_path = rel_target(sheet_part, target)
                table_tree = package._xml(table_path)
                headers = [item.attrib.get("name", "") for item in table_tree.findall("./main:tableColumns/main:tableColumn", NS)]
                table_ref = table_tree.attrib.get("ref", "")
                table_name = table_tree.attrib.get("displayName") or table_tree.attrib.get("name") or Path(table_path).stem
                start_row, start_col, end_row, end_col = parse_range(table_ref)
                rows = extract_table_rows(sheet_cells, table_ref)
                tables.append(
                    {
                        "sheet": sheet_name,
                        "name": table_name,
                        "topLeft": address(start_row, start_col),
                        "range": table_ref,
                        "headers": headers,
                        "rows": rows,
                    }
                )
                mappings.append(
                    {
                        "sheet": sheet_name,
                        "table": table_name,
                        "range": table_ref,
                        "headers": [
                            {
                                "header": header,
                                "column": index_to_col(start_col + index),
                                "headerCell": address(start_row, start_col + index),
                                "dataRange": f"{address(start_row + 1, start_col + index)}:{address(end_row, start_col + index)}",
                            }
                            for index, header in enumerate(headers)
                        ],
                    }
                )
                sheet_tables.append({"name": table_name, "range": table_ref})

            for cf in sheet_tree.findall("./main:conditionalFormatting", NS):
                sqref = cf.attrib.get("sqref", "")
                for rule in cf.findall("./main:cfRule", NS):
                    dxf_id = rule.attrib.get("dxfId")
                    dxf = package.dxfs[int(dxf_id)] if dxf_id is not None and int(dxf_id) < len(package.dxfs) else {}
                    conditional_rules.append(
                        {
                            "id": rule.attrib.get("id") or f"{sheet_name}:{sqref}:{rule.attrib.get('priority', '')}",
                            "sheet": sheet_name,
                            "address": sqref,
                            "type": rule.attrib.get("type"),
                            "formula": (rule.findtext("./main:formula", default="", namespaces=NS) or "").strip(),
                            "priority": int(rule.attrib.get("priority", "0") or 0),
                            "stopIfTrue": rule.attrib.get("stopIfTrue") == "1",
                            "format": dxf,
                        }
                    )

            sheets.append(
                {
                    "name": sheet_name,
                    "sheetId": package.sheet_ids_by_path.get(sheet_part),
                    "path": sheet_part,
                    "tables": sheet_tables,
                    "conditionalFormattingRuleCount": sum(1 for item in conditional_rules if item["sheet"] == sheet_name),
                }
            )

        connections = []
        if package.exists("xl/connections.xml"):
            root = package._xml("xl/connections.xml")
            for item in root.findall("./main:connection", NS):
                db_pr = item.find("./main:dbPr", NS)
                connections.append(
                    {
                        "name": item.attrib.get("name", ""),
                        "description": item.attrib.get("description", ""),
                        "type": item.attrib.get("type", ""),
                        "background": item.attrib.get("background") == "1",
                        "connection": db_pr.attrib.get("connection", "") if db_pr is not None else "",
                        "command": db_pr.attrib.get("command", "") if db_pr is not None else "",
                    }
                )

        data_mashup = extract_data_mashup(package)
        queries = data_mashup.get("queries", [])
        if not queries:
            queries = [
                {
                    "name": connection["name"].removeprefix("Query - ").strip(),
                    "description": connection["description"],
                    "formula": None,
                    "source": "connection-name",
                }
                for connection in connections
                if connection["name"].startswith("Query - ")
            ]

        vba_present = package.exists("xl/vbaProject.bin")
        return {
            "engine": "ooxml",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "workbook": {
                "path": str(workbook_path),
                "name": workbook_path.name,
                "format": workbook_path.suffix.lower(),
                "sha256": sha256_file(workbook_path),
            },
            "sheets": sheets,
            "tables": tables,
            "tableMappings": mappings,
            "names": names,
            "conditionalFormatting": conditional_rules,
            "connections": connections,
            "queries": queries,
            "powerQuery": {
                "dataMashupPresent": data_mashup.get("present", False),
                "dataMashupSha256": data_mashup.get("sha256"),
                "packageEntries": data_mashup.get("entries", []),
            },
            "vba": {
                "present": vba_present,
                "sha256": sha256_bytes(package.read_bytes("xl/vbaProject.bin")) if vba_present else None,
                "size": len(package.read_bytes("xl/vbaProject.bin")) if vba_present else 0,
                "accessible": False,
                "components": [],
                "references": [],
            },
        }
    finally:
        package.close()


def excel_available() -> bool:
    return os.name == "nt" and shutil.which("powershell") is not None


def choose_engine(engine: str) -> str:
    if engine != "auto":
        return engine
    return "com" if excel_available() else "ooxml"


def powershell_json(script: Path, arguments: list[str], timeout: int | None = None) -> dict[str, Any]:
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        *arguments,
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"{script.name} failed")
    stdout = completed.stdout.strip()
    if not stdout:
        return {}
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        json_start = min((index for index in [stdout.find("{"), stdout.find("[")] if index >= 0), default=-1)
        json_end = max(stdout.rfind("}"), stdout.rfind("]"))
        if json_start >= 0 and json_end > json_start:
            return json.loads(stdout[json_start : json_end + 1])
        raise


def extract_com(
    workbook_path: Path,
    output_root: Path | None = None,
    visible: bool = False,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    workbook_path = workbook_path.resolve()
    arguments = ["-WorkbookPath", str(workbook_path)]
    if output_root is not None:
        arguments.extend(["-OutputRoot", str(output_root.resolve())])
    if visible:
        arguments.append("-Visible")
    try:
        return powershell_json(SCRIPT_DIR / "extract-com.ps1", arguments, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        return {
            "engine": "com",
            "available": False,
            "timedOut": True,
            "timeoutSeconds": timeout_seconds,
            "workbook": str(workbook_path),
        }
    except RuntimeError as exc:
        return {
            "engine": "com",
            "available": False,
            "failed": True,
            "error": str(exc),
            "workbook": str(workbook_path),
        }


def com_extract_status(com_result: dict[str, Any] | None) -> str:
    if not com_result:
        return "not_attempted"
    if com_result.get("timedOut"):
        return "timed_out"
    if com_result.get("failed"):
        return "failed"
    return "ok"


def com_extract_succeeded(com_result: dict[str, Any] | None) -> bool:
    return com_extract_status(com_result) == "ok"


def run_mutation(
    workbook_path: Path,
    report_path: Path,
    visible: bool = False,
    timeout_seconds: int = 120,
    scenario_set: str = "full",
) -> dict[str, Any]:
    arguments = [
        "-WorkbookPath",
        str(workbook_path.resolve()),
        "-ReportPath",
        str(report_path.resolve()),
        "-ScenarioSet",
        scenario_set,
    ]
    if visible:
        arguments.append("-Visible")
    try:
        return powershell_json(SCRIPT_DIR / "mutate-workbook.ps1", arguments, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        return {
            "ran": False,
            "timedOut": True,
            "timeoutSeconds": timeout_seconds,
            "workbook": str(workbook_path),
        }


def write_ooxml_snapshot(workbook_path: Path, output_root: Path) -> None:
    snapshot_root = output_root / "ooxml-parts"
    ensure_dir(snapshot_root)
    with zipfile.ZipFile(workbook_path) as workbook_zip:
        for name in workbook_zip.namelist():
            target = snapshot_root / name
            ensure_dir(target.parent)
            target.write_bytes(workbook_zip.read(name))


def write_query_files(queries: list[dict[str, Any]], output_root: Path) -> list[str]:
    query_root = output_root / "power_query" / "queries"
    ensure_dir(query_root)
    written: list[str] = []
    used_names: dict[str, int] = {}
    for index, query in enumerate(queries, start=1):
        formula = query.get("formula")
        if not isinstance(formula, str) or not formula.strip():
            continue
        query_name = str(query.get("name") or f"query-{index}")
        stem = safe_filename(query_name)
        suffix = used_names.get(stem, 0)
        used_names[stem] = suffix + 1
        if suffix:
            stem = f"{stem}-{suffix + 1}"
        target = query_root / f"{stem}.pq"
        target.write_text(formula.rstrip() + "\n", encoding="utf-8")
        written.append(str(target.relative_to(output_root)).replace("\\", "/"))
    return written


def write_default_artifacts(normalized: dict[str, Any], output_root: Path, workbook_path: Path) -> None:
    ensure_dir(output_root)
    write_json(output_root / "normalized.json", normalized)
    write_json(output_root / "workbook_structure" / "tables.json", {"tables": normalized["tables"]})
    write_json(output_root / "workbook_structure" / "table_mappings.json", {"tables": normalized["tableMappings"]})
    write_json(output_root / "workbook_structure" / "names.json", {"names": normalized["names"]})
    write_json(output_root / "workbook_structure" / "conditional_formatting.json", {"rules": normalized["conditionalFormatting"]})
    write_json(output_root / "power_query" / "connections.json", {"connections": normalized["connections"]})
    write_json(output_root / "power_query" / "queries.json", {"queries": normalized["queries"]})
    write_json(output_root / "power_query" / "query_files.json", {"files": write_query_files(normalized["queries"], output_root)})
    write_json(
        output_root / "vba" / "vba_project.json",
        {
            "accessible": normalized["vba"].get("accessible", False),
            "components": normalized["vba"].get("components", []),
            "sha256": normalized["vba"].get("sha256"),
            "size": normalized["vba"].get("size"),
        },
    )
    write_json(
        output_root / "vba" / "vba_references.json",
        {
            "accessible": normalized["vba"].get("accessible", False),
            "references": normalized["vba"].get("references", []),
        },
    )
    write_ooxml_snapshot(workbook_path, output_root)
    with zipfile.ZipFile(workbook_path) as workbook_zip:
        for candidate in [name for name in workbook_zip.namelist() if name.startswith("customXml/item") and name.endswith(".xml")]:
            raw = workbook_zip.read(candidate)
            for encoding in ("utf-16", "utf-8"):
                try:
                    text = raw.decode(encoding)
                except UnicodeDecodeError:
                    continue
                if "<DataMashup" in text:
                    target = output_root / "power_query" / "data_mashup.xml"
                    ensure_dir(target.parent)
                    target.write_text(text, encoding="utf-8")
                    break
        if "xl/vbaProject.bin" in workbook_zip.namelist():
            target = output_root / "vba" / "vbaProject.bin"
            ensure_dir(target.parent)
            target.write_bytes(workbook_zip.read("xl/vbaProject.bin"))


def merge_ooxml_and_com(ooxml_result: dict[str, Any], com_result: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(ooxml_result))
    merged["comDiagnostics"] = {
        "status": com_extract_status(com_result),
        "details": com_result,
    }
    if com_extract_succeeded(com_result):
        merged["engine"] = "com"
        for key in ("sheets", "tables", "tableMappings", "names", "conditionalFormatting", "connections", "queries"):
            if key in com_result and com_result[key]:
                merged[key] = com_result[key]
        if "vba" in com_result:
            merged["vba"] = com_result["vba"]
    return merged


def pull_workbook(workbook_path: Path, output_root: Path, engine: str, visible: bool = False) -> dict[str, Any]:
    ooxml_result = extract_ooxml(workbook_path)
    chosen_engine = choose_engine(engine)
    merged = ooxml_result
    if chosen_engine == "com":
        com_result = extract_com(workbook_path, output_root=output_root, visible=visible)
        merged = merge_ooxml_and_com(ooxml_result, com_result)
    write_default_artifacts(merged, output_root, workbook_path)
    return merged


def normalize_name_formula(value: Any) -> str:
    return str(value or "").strip().upper()


def is_internal_name(name_item: dict[str, Any]) -> bool:
    name = str(name_item.get("name") or "")
    refers_to = normalize_name_formula(name_item.get("refersTo"))
    hidden = bool(name_item.get("hidden"))
    if name.startswith(INTERNAL_NAME_PREFIXES):
        return True
    if hidden and refers_to in {"", "=#NAME?", "#NAME?", "=#REF!", "#REF!"}:
        return True
    return False


def partition_names(names: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    filtered: list[dict[str, Any]] = []
    for item in names:
        if is_internal_name(item):
            filtered.append(item)
        else:
            kept.append(item)
    return kept, filtered


def build_compare_section(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "sheetCount": [len(left.get("sheets", [])), len(right.get("sheets", []))],
        "tableCount": [len(left.get("tables", [])), len(right.get("tables", []))],
        "nameCount": [len(left.get("names", [])), len(right.get("names", []))],
        "conditionalFormattingRuleCount": [len(left.get("conditionalFormatting", [])), len(right.get("conditionalFormatting", []))],
        "connectionCount": [len(left.get("connections", [])), len(right.get("connections", []))],
        "queryCount": [len(left.get("queries", [])), len(right.get("queries", []))],
        "vbaAccessible": [bool(left.get("vba", {}).get("accessible")), bool(right.get("vba", {}).get("accessible"))],
        "vbaComponentCount": [len(left.get("vba", {}).get("components", [])), len(right.get("vba", {}).get("components", []))],
    }
    mismatches = {key: value for key, value in summary.items() if value[0] != value[1]}
    left_vba_hash = left.get("vba", {}).get("sha256")
    right_vba_hash = right.get("vba", {}).get("sha256")
    vba_hash = {
        "left": left_vba_hash,
        "right": right_vba_hash,
        "comparable": bool(left_vba_hash and right_vba_hash),
    }
    if left_vba_hash and right_vba_hash:
        vba_hash["status"] = "match" if left_vba_hash == right_vba_hash else "mismatch"
        if left_vba_hash != right_vba_hash:
            mismatches["vbaSha256"] = [left_vba_hash, right_vba_hash]
    elif left_vba_hash or right_vba_hash:
        vba_hash["status"] = "unavailable_on_one_side"
    else:
        vba_hash["status"] = "unavailable_on_both_sides"
    return {
        "summary": summary,
        "mismatches": mismatches,
        "match": not mismatches,
        "diagnostics": {
            "vbaHash": vba_hash,
        },
    }


def compare_results(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    raw = build_compare_section(left, right)
    left_normalized = json.loads(json.dumps(left))
    right_normalized = json.loads(json.dumps(right))
    left_normalized["names"], left_filtered_names = partition_names(left_normalized.get("names", []))
    right_normalized["names"], right_filtered_names = partition_names(right_normalized.get("names", []))
    normalized = build_compare_section(left_normalized, right_normalized)
    normalized["diagnostics"]["filteredNames"] = {
        "left": left_filtered_names,
        "right": right_filtered_names,
        "leftCount": len(left_filtered_names),
        "rightCount": len(right_filtered_names),
    }
    return {
        "leftEngine": left.get("engine"),
        "rightEngine": right.get("engine"),
        "raw": raw,
        "normalized": normalized,
        "summary": raw["summary"],
        "mismatches": raw["mismatches"],
        "match": raw["match"],
    }


def compare_workbook(workbook_path: Path, output_root: Path, engine: str, visible: bool = False) -> dict[str, Any]:
    ensure_dir(output_root)
    ooxml_result = extract_ooxml(workbook_path)
    if choose_engine(engine) == "com":
        com_result = extract_com(workbook_path, output_root=output_root / "com", visible=visible)
        if com_extract_succeeded(com_result):
            result = compare_results(ooxml_result, merge_ooxml_and_com(ooxml_result, com_result))
        else:
            status = com_extract_status(com_result)
            result = {
                "leftEngine": ooxml_result.get("engine"),
                "rightEngine": "com",
                "raw": {
                    "summary": {},
                    "mismatches": {"comExtraction": ["completed", status]},
                    "match": False,
                    "diagnostics": {"vbaHash": {"left": ooxml_result.get("vba", {}).get("sha256"), "right": None, "comparable": False, "status": "unavailable_on_one_side"}},
                },
                "normalized": {
                    "summary": {},
                    "mismatches": {"comExtraction": ["completed", status]},
                    "match": False,
                    "diagnostics": {
                        "vbaHash": {"left": ooxml_result.get("vba", {}).get("sha256"), "right": None, "comparable": False, "status": "unavailable_on_one_side"},
                        "filteredNames": {"left": [], "right": [], "leftCount": 0, "rightCount": 0},
                    },
                },
                "summary": {},
                "mismatches": {"comExtraction": ["completed", status]},
                "match": False,
                "comDiagnostics": com_result,
            }
    else:
        result = compare_results(ooxml_result, ooxml_result)
    write_json(output_root / "compare.json", result)
    return result


def workbook_supports_tr_regressions(extracted: dict[str, Any]) -> bool:
    sheet_names = {item["name"] for item in extracted.get("sheets", [])}
    table_names = {item["name"] for item in extracted.get("tables", [])}
    return {"AP_INVOICES_INTERFACE", "AP_INVOICE_LINES_INTERFACE"} <= sheet_names and {"tbl_invoices", "tbl_invoice_lines"} <= table_names


def run_tr_regressions(workbook_path: Path) -> list[dict[str, Any]]:
    script_dir = SKILL_ROOT / "tests" / "fixtures" / "tr_upload_sheet" / "scripts"
    script_names = [
        "test-deferred-sheet-exit.ps1",
        "test-invoice-number-sequencing.ps1",
        "test-invoice-number-interior-edit.ps1",
        "test-invoice-number-format-propagation.ps1",
        "test-invoice-number-stock-vin-patterns.ps1",
        "test-export-zip-import-set.ps1",
    ]
    results = []
    for script_name in script_names:
        script_path = script_dir / script_name
        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-WorkbookPath",
            str(workbook_path),
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=60)
            results.append(
                {
                    "script": script_name,
                    "passed": completed.returncode == 0,
                    "stdout": completed.stdout.strip(),
                    "stderr": completed.stderr.strip(),
                }
            )
        except subprocess.TimeoutExpired as exc:
            results.append(
                {
                    "script": script_name,
                    "passed": False,
                    "stdout": (exc.stdout or "").strip(),
                    "stderr": ((exc.stderr or "").strip() or "timed out after 60 seconds"),
                }
            )
    return results


def audit_workbook(
    workbook_path: Path,
    output_root: Path,
    engine: str,
    visible: bool = False,
    include_regressions: bool = False,
    scenario_set: str = "full",
    run_root: Path | None = None,
) -> dict[str, Any]:
    if run_root is None:
        run_root = output_root / "audits" / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{slugify(workbook_path.stem)}"
    ensure_dir(run_root)
    original_copy_root = run_root / "original-copy"
    reports_root = run_root / "reports"
    working_copy = original_copy_root / workbook_path.name
    ensure_dir(original_copy_root)
    ensure_dir(reports_root)
    shutil.copy2(workbook_path, working_copy)

    baseline_root = run_root / "baseline"
    mutated_root = run_root / "post-mutation"
    baseline = pull_workbook(working_copy, baseline_root, engine=engine, visible=visible)
    baseline_compare = compare_workbook(working_copy, reports_root / "baseline-compare", engine=engine, visible=visible)
    mutation_report = (
        run_mutation(working_copy, reports_root / "mutation-report.json", visible=visible, scenario_set=scenario_set)
        if excel_available()
        else {"ran": False, "skipped": True, "reason": "excel_unavailable", "scenarios": []}
    )
    if mutation_report.get("timedOut"):
        mutated = baseline
        delta = {
            "leftEngine": baseline.get("engine"),
            "rightEngine": baseline.get("engine"),
            "match": False,
            "mismatches": {"mutation": ["completed", "timed_out"]},
            "summary": {},
        }
        post_mutation_compare = {
            "leftEngine": baseline.get("engine"),
            "rightEngine": baseline.get("engine"),
            "raw": {"summary": {}, "mismatches": {"mutation": ["completed", "timed_out"]}, "match": False, "diagnostics": {}},
            "normalized": {
                "summary": {},
                "mismatches": {"mutation": ["completed", "timed_out"]},
                "match": False,
                "diagnostics": {"filteredNames": {"left": [], "right": [], "leftCount": 0, "rightCount": 0}},
            },
            "summary": {},
            "mismatches": {"mutation": ["completed", "timed_out"]},
            "match": False,
        }
    else:
        mutated = pull_workbook(working_copy, mutated_root, engine=engine, visible=visible)
        post_mutation_compare = compare_workbook(working_copy, reports_root / "post-mutation-compare", engine=engine, visible=visible)
        delta = compare_results(baseline, mutated)
    regressions = (
        run_tr_regressions(working_copy)
        if include_regressions and excel_available() and workbook_supports_tr_regressions(baseline)
        else []
    )
    report = {
        "workbook": str(workbook_path),
        "workingCopy": str(working_copy),
        "engine": choose_engine(engine),
        "baselineRoot": str(baseline_root),
        "mutatedRoot": str(mutated_root),
        "reportsRoot": str(reports_root),
        "baselineComStatus": baseline.get("comDiagnostics", {}).get("status", "not_attempted"),
        "mutatedComStatus": mutated.get("comDiagnostics", {}).get("status", "not_attempted"),
        "scenarioSet": scenario_set,
        "baselineCompare": baseline_compare,
        "postMutationCompare": post_mutation_compare,
        "mutationReport": mutation_report,
        "delta": delta,
        "regressions": regressions,
    }
    write_json(reports_root / "report.json", report)
    return report


def render_matrix_summary(summary: dict[str, Any]) -> str:
    lines = [
        "# Excel Workbook Sync Matrix Audit",
        "",
        f"- Generated: {summary['generatedAt']}",
        f"- Engine: {summary['engine']}",
        f"- Workbooks: {len(summary['workbooks'])}",
        "",
        "| Workbook | Raw Compare | Normalized Compare | Delta | Scenarios |",
        "| --- | --- | --- | --- | --- |",
    ]
    for workbook in summary["workbooks"]:
        lines.append(
            "| {name} | {raw} | {normalized} | {delta} | {scenarios} |".format(
                name=workbook["workbookName"],
                raw="pass" if workbook["baselineRawMatch"] else "fail",
                normalized="pass" if workbook["baselineNormalizedMatch"] else "fail",
                delta="pass" if workbook["deltaMatch"] else "fail",
                scenarios=workbook["scenarioCount"],
            )
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def matrix_audit_workbooks(
    workbook_paths: list[Path],
    output_root: Path,
    engine: str,
    visible: bool = False,
    include_regressions: bool = False,
    scenario_set: str = "full",
) -> dict[str, Any]:
    run_root = output_root / f"matrix-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    ensure_dir(run_root)
    reports = []
    for index, workbook_path in enumerate(workbook_paths, start=1):
        workbook_root = run_root / f"{index:02d}-{slugify(workbook_path.stem)}"
        report = audit_workbook(
            workbook_path,
            output_root,
            engine,
            visible=visible,
            include_regressions=include_regressions,
            scenario_set=scenario_set,
            run_root=workbook_root,
        )
        reports.append(
            {
                "workbook": str(workbook_path),
                "workbookName": workbook_path.name,
                "reportPath": str(workbook_root / "reports" / "report.json"),
                "baselineRawMatch": report["baselineCompare"]["raw"]["match"],
                "baselineNormalizedMatch": report["baselineCompare"]["normalized"]["match"],
                "postMutationRawMatch": report["postMutationCompare"]["raw"]["match"],
                "postMutationNormalizedMatch": report["postMutationCompare"]["normalized"]["match"],
                "deltaMatch": report["delta"]["match"],
                "scenarioCount": len(report["mutationReport"].get("scenarios", [])),
            }
        )
    summary = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "engine": choose_engine(engine),
        "runRoot": str(run_root),
        "workbooks": reports,
    }
    write_json(run_root / "matrix-summary.json", summary)
    (run_root / "matrix-summary.md").write_text(render_matrix_summary(summary), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Portable Excel workbook sync and audit CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--workbook", required=True, type=Path)
        subparser.add_argument("--engine", choices=["auto", "ooxml", "com"], default="auto")
        subparser.add_argument("--visible", action="store_true")

    pull_parser = subparsers.add_parser("pull")
    add_common(pull_parser)
    pull_parser.add_argument("--output-root", required=True, type=Path)

    compare_parser = subparsers.add_parser("compare")
    add_common(compare_parser)
    compare_parser.add_argument("--output-root", required=True, type=Path)

    audit_parser = subparsers.add_parser("audit")
    add_common(audit_parser)
    audit_parser.add_argument("--output-root", required=True, type=Path)
    audit_parser.add_argument("--include-regressions", action="store_true")
    audit_parser.add_argument("--scenario-set", choices=["full"], default="full")

    matrix_parser = subparsers.add_parser("matrix-audit")
    matrix_parser.add_argument("--workbook", required=True, action="append", type=Path)
    matrix_parser.add_argument("--output-root", required=True, type=Path)
    matrix_parser.add_argument("--engine", choices=["auto", "ooxml", "com"], default="auto")
    matrix_parser.add_argument("--visible", action="store_true")
    matrix_parser.add_argument("--include-regressions", action="store_true")
    matrix_parser.add_argument("--scenario-set", choices=["full"], default="full")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "pull":
        result = pull_workbook(args.workbook, args.output_root, args.engine, visible=args.visible)
    elif args.command == "compare":
        result = compare_workbook(args.workbook, args.output_root, args.engine, visible=args.visible)
    elif args.command == "audit":
        result = audit_workbook(
            args.workbook,
            args.output_root,
            args.engine,
            visible=args.visible,
            include_regressions=args.include_regressions,
            scenario_set=args.scenario_set,
        )
    elif args.command == "matrix-audit":
        result = matrix_audit_workbooks(
            args.workbook,
            args.output_root,
            args.engine,
            visible=args.visible,
            include_regressions=args.include_regressions,
            scenario_set=args.scenario_set,
        )
    else:
        raise AssertionError(f"unsupported command: {args.command}")
    print(json.dumps(normalize_json(result), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
