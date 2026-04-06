from __future__ import annotations

import argparse
import base64
import io
import json
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path, PurePosixPath
from typing import Any


NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "custom": "http://schemas.openxmlformats.org/officeDocument/2006/customXml",
}

SUPPORTED_CF_TYPES = {
    "expression",
    "cell-value",
    "unique-values",
    "top10",
    "above-average",
    "color-scale",
    "data-bar",
    "icon-set",
}


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _column_letter_to_index(column: str) -> int:
    value = 0
    for char in column.upper():
        value = (value * 26) + (ord(char) - ord("A") + 1)
    return value


def _cell_ref_to_row_col(cell_ref: str) -> tuple[int, int]:
    match = re.match(r"^([A-Za-z]+)(\d+)$", cell_ref)
    if not match:
        raise ValueError(f"Unsupported cell reference: {cell_ref}")
    return int(match.group(2)), _column_letter_to_index(match.group(1))


def _range_ref_to_bounds(range_ref: str) -> tuple[int, int, int, int]:
    if ":" in range_ref:
        start_ref, end_ref = range_ref.split(":", 1)
    else:
        start_ref = end_ref = range_ref
    start_row, start_col = _cell_ref_to_row_col(start_ref.replace("$", ""))
    end_row, end_col = _cell_ref_to_row_col(end_ref.replace("$", ""))
    return start_row, start_col, end_row, end_col


def _normalize_rel_target(base_path: str, target: str) -> str:
    if PurePosixPath(target).is_absolute():
        return target.lstrip("/")
    rel_path = PurePosixPath(base_path)
    if rel_path.parent.name == "_rels" and rel_path.name.endswith(".rels"):
        source_dir = rel_path.parent.parent
        source_name = rel_path.name[:-5]
        base_parts = list((source_dir / source_name).parent.parts)
    else:
        base_parts = list(rel_path.parent.parts)
    for part in PurePosixPath(target).parts:
        if part in ("", "."):
            continue
        if part == "..":
            if base_parts:
                base_parts.pop()
            continue
        base_parts.append(part)
    return str(PurePosixPath(*base_parts))


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", name).strip()
    return cleaned or "query"


class WorkbookPackage:
    def __init__(self, workbook_path: Path) -> None:
        self.workbook_path = workbook_path.resolve()
        self._zip = zipfile.ZipFile(self.workbook_path)
        self.shared_strings = self._load_shared_strings()
        self.workbook_xml = self._read_xml("xl/workbook.xml")
        self.workbook_rels = self._read_relationships("xl/_rels/workbook.xml.rels")
        self.style_date_ids = self._load_style_date_ids()
        self.sheets = self._load_sheets()

    def close(self) -> None:
        self._zip.close()

    def _read_bytes(self, name: str) -> bytes:
        return self._zip.read(name)

    def _read_text(self, name: str) -> str:
        return self._read_bytes(name).decode("utf-8-sig")

    def _read_xml(self, name: str) -> ET.Element:
        return ET.fromstring(self._read_bytes(name))

    def _read_relationships(self, name: str) -> dict[str, dict[str, str]]:
        rels: dict[str, dict[str, str]] = {}
        try:
            root = self._read_xml(name)
        except KeyError:
            return rels
        for child in root.findall("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"):
            rels[child.attrib["Id"]] = {
                "target": _normalize_rel_target(name, child.attrib.get("Target", "")),
                "type": child.attrib.get("Type", ""),
            }
        return rels

    def _load_shared_strings(self) -> list[str]:
        try:
            root = self._read_xml("xl/sharedStrings.xml")
        except KeyError:
            return []
        values: list[str] = []
        for si in root.findall("main:si", NS):
            parts = []
            for node in si.iter():
                if _local_name(node.tag) == "t":
                    parts.append(node.text or "")
            values.append("".join(parts))
        return values

    def _load_style_date_ids(self) -> set[int]:
        try:
            root = self._read_xml("xl/styles.xml")
        except KeyError:
            return set()
        custom_dates = set()
        numfmts = root.find("main:numFmts", NS)
        if numfmts is not None:
            for fmt in numfmts.findall("main:numFmt", NS):
                try:
                    fmt_id = int(fmt.attrib.get("numFmtId", "0"))
                except ValueError:
                    continue
                code = (fmt.attrib.get("formatCode", "") or "").lower()
                if any(token in code for token in ("yy", "dd", "mm", "hh", "ss")):
                    custom_dates.add(fmt_id)
        date_ids = set(range(14, 23)) | set(range(27, 37)) | {45, 46, 47, 50, 57}
        date_ids.update(custom_dates)
        style_date_ids: set[int] = set()
        cellxfs = root.find("main:cellXfs", NS)
        if cellxfs is None:
            return style_date_ids
        for index, xf in enumerate(cellxfs.findall("main:xf", NS)):
            try:
                num_fmt_id = int(xf.attrib.get("numFmtId", "0"))
            except ValueError:
                continue
            if num_fmt_id in date_ids:
                style_date_ids.add(index)
        return style_date_ids

    def _load_sheets(self) -> list[dict[str, Any]]:
        sheets = []
        for sheet in self.workbook_xml.findall("main:sheets/main:sheet", NS):
            rel_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            rel = self.workbook_rels.get(rel_id or "")
            if not rel:
                continue
            sheets.append(
                {
                    "name": sheet.attrib.get("name", ""),
                    "sheetId": sheet.attrib.get("sheetId", ""),
                    "path": rel["target"],
                    "rels": self._read_relationships(f"xl/worksheets/_rels/{PurePosixPath(rel['target']).name}.rels"),
                }
            )
        return sheets

    def _convert_scalar(self, value: str, cell_type: str | None, style_id: int | None) -> Any:
        if cell_type == "s":
            try:
                return self.shared_strings[int(value)]
            except Exception:
                return value
        if cell_type == "b":
            return value == "1"
        if cell_type == "str":
            return value
        if cell_type == "inlineStr":
            return value
        if cell_type == "e":
            return value
        if value == "":
            return ""
        try:
            number = float(value)
        except ValueError:
            return value
        if style_id is not None and style_id in self.style_date_ids:
            return number
        if number.is_integer():
            return int(number)
        return number

    def _read_sheet_cells(self, sheet_path: str) -> dict[tuple[int, int], Any]:
        root = self._read_xml(sheet_path)
        cells: dict[tuple[int, int], Any] = {}
        sheet_data = root.find("main:sheetData", NS)
        if sheet_data is None:
            return cells
        for row in sheet_data.findall("main:row", NS):
            for cell in row.findall("main:c", NS):
                cell_ref = cell.attrib.get("r")
                if not cell_ref:
                    continue
                cell_type = cell.attrib.get("t")
                style_id = None
                if "s" in cell.attrib:
                    try:
                        style_id = int(cell.attrib["s"])
                    except ValueError:
                        style_id = None
                if cell_type == "inlineStr":
                    inline = cell.find("main:is", NS)
                    if inline is None:
                        value = ""
                    else:
                        value = "".join((node.text or "") for node in inline.iter() if _local_name(node.tag) == "t")
                else:
                    value_node = cell.find("main:v", NS)
                    formula_node = cell.find("main:f", NS)
                    if value_node is not None:
                        value = value_node.text or ""
                    elif formula_node is not None:
                        value = ""
                    else:
                        value = ""
                cells[_cell_ref_to_row_col(cell_ref)] = self._convert_scalar(value, cell_type, style_id)
        return cells

    def _resolve_table_query_loads(self) -> dict[str, list[dict[str, Any]]]:
        loads: dict[str, list[dict[str, Any]]] = {}
        for sheet in self.sheets:
            table_rels = {rel["target"]: rel_id for rel_id, rel in sheet["rels"].items() if rel["type"].endswith("/table")}
            query_table_map: dict[str, int] = {}
            for target in table_rels:
                table_xml = self._read_xml(target)
                query_rel = self._read_relationships(f"xl/tables/_rels/{PurePosixPath(target).name}.rels")
                for rel in query_rel.values():
                    if rel["type"].endswith("/queryTable"):
                        query_table_xml = self._read_xml(rel["target"])
                        try:
                            connection_id = int(query_table_xml.attrib.get("connectionId", "0"))
                        except ValueError:
                            continue
                        query_table_map[target] = connection_id
            for target, connection_id in query_table_map.items():
                table_xml = self._read_xml(target)
                connection_name = None
                try:
                    connections = self.parse_connections()
                    for connection in connections:
                        if connection.get("_id") == connection_id:
                            connection_name = connection.get("name")
                            break
                except Exception:
                    connection_name = None
                if not connection_name:
                    continue
                loads.setdefault(connection_name, []).append(
                    {
                        "connectionName": connection_name,
                        "destinationType": "worksheet-table",
                        "sheet": sheet["name"],
                        "table": table_xml.attrib.get("name", ""),
                        "topLeft": table_xml.attrib.get("ref", "").split(":", 1)[0],
                    }
                )
        return loads

    def parse_tables(self) -> list[dict[str, Any]]:
        tables: list[dict[str, Any]] = []
        for sheet in self.sheets:
            sheet_xml = self._read_xml(sheet["path"])
            cells = self._read_sheet_cells(sheet["path"])
            table_parts = sheet_xml.find("main:tableParts", NS)
            if table_parts is None:
                continue
            for table_part in table_parts.findall("main:tablePart", NS):
                rel_id = table_part.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                rel = sheet["rels"].get(rel_id or "")
                if not rel:
                    continue
                table_xml = self._read_xml(rel["target"])
                ref = table_xml.attrib.get("ref", "")
                start_row, start_col, end_row, end_col = _range_ref_to_bounds(ref)
                headers = []
                for col in range(start_col, end_col + 1):
                    headers.append(cells.get((start_row, col), ""))
                rows = []
                header_row_count = int(table_xml.attrib.get("headerRowCount", "1") or "1")
                totals_row_count = int(table_xml.attrib.get("totalsRowCount", "0") or "0")
                data_start = start_row + header_row_count
                data_end = end_row - totals_row_count
                for row in range(data_start, data_end + 1):
                    rows.append([cells.get((row, col)) for col in range(start_col, end_col + 1)])
                tables.append(
                    {
                        "sheet": sheet["name"],
                        "name": table_xml.attrib.get("name", ""),
                        "topLeft": ref.split(":", 1)[0],
                        "headers": headers,
                        "rows": rows,
                    }
                )
        return sorted(tables, key=lambda entry: (entry["sheet"], entry["name"]))

    def parse_names(self) -> list[dict[str, Any]]:
        names = []
        defined_names = self.workbook_xml.find("main:definedNames", NS)
        if defined_names is None:
            return names
        for defined in defined_names.findall("main:definedName", NS):
            names.append(
                {
                    "name": defined.attrib.get("name", ""),
                    "refersTo": defined.text or "",
                }
            )
        return sorted(names, key=lambda entry: entry["name"].lower())

    def parse_connections(self) -> list[dict[str, Any]]:
        try:
            root = self._read_xml("xl/connections.xml")
        except KeyError:
            return []
        connections = []
        for connection in root.findall("main:connection", NS):
            entry: dict[str, Any] = {
                "_id": int(connection.attrib.get("id", "0") or "0"),
                "name": connection.attrib.get("name", ""),
                "type": "type-" + (connection.attrib.get("type", "") or "0"),
                "rawType": int(connection.attrib.get("type", "0") or "0"),
                "description": connection.attrib.get("description", ""),
                "oledb": None,
                "model": None,
                "worksheetDataConnection": None,
            }
            raw_type = entry["rawType"]
            entry["type"] = {
                1: "ole-db",
                2: "odbc",
                3: "worksheet",
                4: "text",
                5: "web",
                6: "model",
            }.get(raw_type, f"type-{raw_type}")
            dbpr = connection.find("main:dbPr", NS)
            if dbpr is not None:
                entry["oledb"] = {
                    "connection": dbpr.attrib.get("connection"),
                    "commandText": dbpr.attrib.get("command"),
                    "commandType": dbpr.attrib.get("commandType"),
                    "backgroundQuery": connection.attrib.get("background") == "1",
                    "refreshOnFileOpen": connection.attrib.get("refreshOnLoad") == "1",
                    "refreshWithRefreshAll": None,
                    "enableRefresh": connection.attrib.get("deleted") != "1",
                }
            connections.append(entry)
        return sorted(connections, key=lambda entry: entry["name"])

    def parse_conditional_formatting(self) -> list[dict[str, Any]]:
        rules: list[dict[str, Any]] = []
        for sheet in self.sheets:
            root = self._read_xml(sheet["path"])
            for cf_group in root.findall("main:conditionalFormatting", NS):
                sqref = cf_group.attrib.get("sqref", "")
                for index, rule in enumerate(cf_group.findall("main:cfRule", NS), start=1):
                    raw_type = rule.attrib.get("type", "expression")
                    mapped_type = {
                        "expression": "expression",
                        "cellIs": "cell-value",
                        "duplicateValues": "unique-values",
                        "uniqueValues": "unique-values",
                        "top10": "top10",
                        "aboveAverage": "above-average",
                        "colorScale": "color-scale",
                        "dataBar": "data-bar",
                        "iconSet": "icon-set",
                    }.get(raw_type, raw_type)
                    entry: dict[str, Any] = {
                        "id": f"CF-{sheet['name']}-{len(rules) + 1:03d}",
                        "sheet": sheet["name"],
                        "type": mapped_type,
                        "supported": mapped_type in SUPPORTED_CF_TYPES,
                        "priority": int(rule.attrib.get("priority", "0") or "0") or None,
                        "stopIfTrue": rule.attrib.get("stopIfTrue") == "1" if "stopIfTrue" in rule.attrib else None,
                        "address": sqref.replace(" ", ","),
                        "formula": None,
                        "format": {
                            "interiorColor": None,
                            "fontColor": None,
                            "bold": None,
                        },
                        "rawType": raw_type,
                    }
                    formula_nodes = [node.text or "" for node in rule.findall("main:formula", NS)]
                    if formula_nodes:
                        entry["formula"] = formula_nodes[0]
                    if mapped_type == "cell-value":
                        entry["operator"] = rule.attrib.get("operator")
                        if len(formula_nodes) > 1:
                            entry["formula2"] = formula_nodes[1]
                    if mapped_type == "unique-values":
                        entry["dupeUnique"] = 0 if raw_type == "duplicateValues" else 1
                    rules.append(entry)
        return sorted(rules, key=lambda entry: (entry["sheet"], entry["priority"] or 0, entry["id"]))

    def _extract_embedded_zip_bytes(self, payload: bytes) -> bytes | None:
        start = payload.find(b"PK\x03\x04")
        if start < 0:
            return None
        end = payload.rfind(b"PK\x05\x06")
        if end < 0 or end + 22 > len(payload):
            return payload[start:]
        if end + 22 <= len(payload):
            comment_length = struct.unpack("<H", payload[end + 20 : end + 22])[0]
            end += 22 + comment_length
        return payload[start:end]

    def _parse_query_sections(self, mashup_zip: zipfile.ZipFile) -> list[dict[str, Any]]:
        queries: list[dict[str, Any]] = []
        for name in mashup_zip.namelist():
            if not name.lower().startswith("formulas/") or not name.lower().endswith(".m"):
                continue
            text = mashup_zip.read(name).decode("utf-8-sig")
            positions = list(re.finditer(r"(?m)^\s*shared\s+((?:#\"[^\"]+\")|(?:[A-Za-z0-9_]+))\s*=\s*", text))
            if not positions:
                query_name = Path(name).stem
                queries.append({"name": query_name, "formula": text})
                continue
            for index, match in enumerate(positions):
                raw_name = match.group(1)
                query_name = raw_name[2:-1] if raw_name.startswith('#"') and raw_name.endswith('"') else raw_name
                expr_start = match.start()
                expr_end = positions[index + 1].start() if index + 1 < len(positions) else len(text)
                queries.append({"name": query_name, "formula": text[expr_start:expr_end].strip()})
        deduped: dict[str, dict[str, Any]] = {}
        for query in queries:
            deduped[query["name"]] = query
        return [deduped[name] for name in sorted(deduped)]

    def _parse_local_zip_entries(self, payload: bytes) -> dict[str, bytes]:
        entries: dict[str, bytes] = {}
        offset = payload.find(b"PK\x03\x04")
        if offset < 0:
            return entries
        while offset + 30 <= len(payload) and payload[offset : offset + 4] == b"PK\x03\x04":
            header = payload[offset + 4 : offset + 30]
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
            ) = struct.unpack("<HHHHHIIIHH", header)
            name_start = offset + 30
            name_end = name_start + name_length
            extra_end = name_end + extra_length
            name = payload[name_start:name_end].decode("utf-8")
            data_start = extra_end
            data_end = data_start + compressed_size
            blob = payload[data_start:data_end]
            if flags & 0x08:
                break
            if compression == 0:
                data = blob
            elif compression == 8:
                data = zlib.decompress(blob, -15)
            else:
                break
            entries[name] = data
            offset = data_end
        return entries

    def _extract_query_formulas(self, payload_bytes: bytes) -> list[dict[str, Any]]:
        zip_bytes = self._extract_embedded_zip_bytes(payload_bytes)
        if not zip_bytes:
            return []
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as mashup_zip:
                if mashup_zip.namelist():
                    return self._parse_query_sections(mashup_zip)
        except zipfile.BadZipFile:
            pass

        queries: list[dict[str, Any]] = []
        for name, data in self._parse_local_zip_entries(zip_bytes).items():
            if not name.lower().startswith("formulas/") or not name.lower().endswith(".m"):
                continue
            text = data.decode("utf-8-sig")
            positions = list(re.finditer(r"(?m)^\s*shared\s+((?:#\"[^\"]+\")|(?:[A-Za-z0-9_]+))\s*=\s*", text))
            if not positions:
                queries.append({"name": Path(name).stem, "formula": text})
                continue
            for index, match in enumerate(positions):
                raw_name = match.group(1)
                query_name = raw_name[2:-1] if raw_name.startswith('#"') and raw_name.endswith('"') else raw_name
                expr_start = match.start()
                expr_end = positions[index + 1].start() if index + 1 < len(positions) else len(text)
                queries.append({"name": query_name, "formula": text[expr_start:expr_end].strip()})
        deduped: dict[str, dict[str, Any]] = {}
        for query in queries:
            deduped[query["name"]] = query
        return [deduped[name] for name in sorted(deduped)]

    def parse_power_query(self) -> dict[str, Any]:
        connections = self.parse_connections()
        loads = self._resolve_table_query_loads()
        mashup_xml = None
        for name in self._zip.namelist():
            if not name.startswith("customXml/item") or not name.endswith(".xml"):
                continue
            try:
                root = self._read_xml(name)
            except ET.ParseError:
                continue
            if _local_name(root.tag) == "DataMashup":
                mashup_xml = root
                break
        if mashup_xml is None:
            return {"queries": [], "connections": connections, "modelTables": []}
        payload_text = "".join(mashup_xml.itertext()).strip()
        payload_bytes = base64.b64decode(payload_text)
        queries = []
        for query in self._extract_query_formulas(payload_bytes):
            preferred_connection_names = [f"Query - {query['name']}", query["name"]]
            connection_name = next((conn["name"] for conn in connections if conn["name"] in preferred_connection_names), None)
            queries.append(
                {
                    "name": query["name"],
                    "description": "",
                    "formula": query["formula"],
                    "connectionName": connection_name,
                    "loads": loads.get(connection_name or "", []),
                    "loadToDataModel": False,
                }
            )
        return {"queries": sorted(queries, key=lambda entry: entry["name"]), "connections": connections, "modelTables": []}


def normalize_surfaces(surface_text: str | None) -> list[str]:
    if not surface_text:
        return []
    aliases = {
        "conditional-formatting": "cf",
        "conditional_formatting": "cf",
        "power-query": "pq",
        "power_query": "pq",
    }
    normalized = []
    for item in surface_text.split(","):
        token = item.strip().lower()
        if not token:
            continue
        normalized.append(aliases.get(token, token))
    return normalized


def build_query_payload(workbook_path: Path, surfaces: list[str]) -> dict[str, Any]:
    package = WorkbookPackage(workbook_path)
    try:
        payload: dict[str, Any] = {
            "workbookPath": str(workbook_path.resolve()),
            "backend": "package",
            "sourceFormat": workbook_path.suffix.lower(),
            "workingPath": str(workbook_path.resolve()),
            "normalization": "none",
            "warnings": [],
            "stagesTried": ["package"],
        }
        if not surfaces or "tables" in surfaces:
            payload["tables"] = package.parse_tables()
        if not surfaces or "names" in surfaces:
            payload["names"] = package.parse_names()
        pq_info = None
        if not surfaces or {"pq", "connections", "model"} & set(surfaces):
            pq_info = package.parse_power_query()
        if not surfaces or "cf" in surfaces:
            payload["cf"] = package.parse_conditional_formatting()
        if pq_info is not None:
            if not surfaces or "pq" in surfaces:
                payload["pq"] = pq_info["queries"]
            if not surfaces or "connections" in surfaces:
                payload["connections"] = pq_info["connections"]
            if not surfaces or "model" in surfaces:
                payload["model"] = {"modelTables": pq_info["modelTables"]}
        return payload
    finally:
        package.close()


def build_inspection_payload(query_payload: dict[str, Any]) -> dict[str, Any]:
    cf = query_payload.get("cf", [])
    model = query_payload.get("model", {}) or {}
    inspection = {
        "workbookPath": query_payload["workbookPath"],
        "backend": query_payload["backend"],
        "sourceFormat": query_payload["sourceFormat"],
        "workingPath": query_payload["workingPath"],
        "normalization": query_payload["normalization"],
        "warnings": query_payload.get("warnings", []),
        "stagesTried": query_payload.get("stagesTried", []),
        "counts": {
            "tables": len(query_payload.get("tables", [])),
            "names": len(query_payload.get("names", [])),
            "cf": len(cf),
            "pq": len(query_payload.get("pq", [])),
            "connections": len(query_payload.get("connections", [])),
            "modelTables": len(model.get("modelTables", [])),
            "vba": len(query_payload.get("vba", [])),
            "references": len(query_payload.get("references", [])),
        },
        "project": query_payload.get("project"),
        "supportedCfTypes": sorted({rule["type"] for rule in cf if rule.get("supported")}),
        "unsupportedCfTypes": sorted({rule["type"] for rule in cf if not rule.get("supported")}),
    }
    return inspection


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _relative_or_absolute(base_dir: Path, target_path: Path) -> str:
    try:
        return str(target_path.resolve().relative_to(base_dir.resolve()))
    except Exception:
        try:
            return str(target_path.resolve().relative_to(base_dir.resolve().parent))
        except Exception:
            return str(target_path.resolve())


def bootstrap_bundle(workbook_path: Path, output_dir: Path, manifest_path: Path | None, surfaces: list[str]) -> dict[str, Any]:
    query_payload = build_query_payload(workbook_path, surfaces)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_path or output_dir / "excel-sync.manifest.json"
    structure_dir = output_dir / "workbook_structure"
    _write_json(structure_dir / "tables.json", {"tables": query_payload.get("tables", [])})
    _write_json(structure_dir / "names.json", {"names": query_payload.get("names", [])})
    _write_json(structure_dir / "conditional_formatting.json", {"rules": query_payload.get("cf", [])})
    manifest: dict[str, Any] = {
        "workbookPath": _relative_or_absolute(manifest_path.parent, workbook_path),
        "vbaComponents": [],
        "structure": {
            "tablesPath": str(PurePosixPath("workbook_structure/tables.json")),
            "namesPath": str(PurePosixPath("workbook_structure/names.json")),
            "conditionalFormattingPath": str(PurePosixPath("workbook_structure/conditional_formatting.json")),
            "tablesDiscovery": {"mode": "all"},
            "namesDiscovery": {"mode": "all", "excludeBuiltIn": True},
            "conditionalFormattingDiscovery": {"mode": "all-major"},
        },
    }
    pq_queries = query_payload.get("pq", [])
    pq_connections = query_payload.get("connections", [])
    pq_model = query_payload.get("model", {}).get("modelTables", [])
    if pq_queries or pq_connections or pq_model:
        pq_dir = output_dir / "power_query" / "queries"
        pq_dir.mkdir(parents=True, exist_ok=True)
        query_entries = []
        used = set()
        for query in pq_queries:
            base = _safe_filename(query["name"])
            filename = f"{base}.pq"
            counter = 1
            while filename in used:
                filename = f"{base}-{counter}.pq"
                counter += 1
            used.add(filename)
            (pq_dir / filename).write_text((query.get("formula") or "").replace("\r\n", "\n"), encoding="utf-8")
            query_entries.append(
                {
                    "name": query["name"],
                    "file": filename,
                    "description": query.get("description", ""),
                    "connectionName": query.get("connectionName"),
                    "loads": query.get("loads", []),
                    "loadToDataModel": bool(query.get("loadToDataModel")),
                }
            )
        _write_json(output_dir / "power_query" / "queries.json", {"queries": query_entries})
        _write_json(output_dir / "power_query" / "connections.json", {"connections": pq_connections})
        _write_json(output_dir / "power_query" / "model.json", {"modelTables": pq_model})
        _write_json(output_dir / "power_query" / "refresh.json", {"queries": [{"name": q["name"], "connectionName": q.get("connectionName")} for q in pq_queries]})
        manifest["powerQuery"] = {
            "queriesDirectory": str(PurePosixPath("power_query/queries")),
            "queriesPath": str(PurePosixPath("power_query/queries.json")),
            "connectionsPath": str(PurePosixPath("power_query/connections.json")),
            "modelPath": str(PurePosixPath("power_query/model.json")),
            "refreshPath": str(PurePosixPath("power_query/refresh.json")),
        }
    _write_json(manifest_path, manifest)
    return {
        "manifestPath": str(manifest_path.resolve()),
        "outputDirectory": str(output_dir.resolve()),
        "backend": "package",
        "sourceFormat": workbook_path.suffix.lower(),
        "workbookPath": str(workbook_path.resolve()),
        "warnings": query_payload.get("warnings", []),
        "stagesTried": query_payload.get("stagesTried", []),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    query_parser = subparsers.add_parser("query")
    query_parser.add_argument("--workbook-path", required=True)
    query_parser.add_argument("--surface", default="")

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--workbook-path", required=True)
    inspect_parser.add_argument("--surface", default="")

    bootstrap_parser = subparsers.add_parser("bootstrap")
    bootstrap_parser.add_argument("--workbook-path", required=True)
    bootstrap_parser.add_argument("--surface", default="")
    bootstrap_parser.add_argument("--output-dir", required=True)
    bootstrap_parser.add_argument("--manifest-path")

    args = parser.parse_args(argv)
    workbook_path = Path(args.workbook_path)
    surfaces = normalize_surfaces(getattr(args, "surface", ""))
    if args.command == "query":
        payload = build_query_payload(workbook_path, surfaces)
    elif args.command == "inspect":
        payload = build_inspection_payload(build_query_payload(workbook_path, surfaces))
    else:
        payload = bootstrap_bundle(
            workbook_path,
            Path(args.output_dir),
            Path(args.manifest_path) if args.manifest_path else None,
            surfaces,
        )
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
