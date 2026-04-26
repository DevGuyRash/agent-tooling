from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import io
import json
import os
import re
import struct
import sys
import tempfile
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
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
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

SKILL_ROOT = Path(__file__).resolve().parents[1]
CAPABILITY_MATRIX_PATH = SKILL_ROOT / "references" / "excel-capability-matrix.json"


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _column_letter_to_index(column: str) -> int:
    value = 0
    for char in column.upper():
        value = (value * 26) + (ord(char) - ord("A") + 1)
    return value


def _column_index_to_letter(index: int) -> str:
    result: list[str] = []
    value = index
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        result.append(chr(ord("A") + remainder))
    return "".join(reversed(result))


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


def _row_col_to_cell_ref(row: int, col: int) -> str:
    return f"{_column_index_to_letter(col)}{row}"


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


def _parse_bool_attr(value: str | None) -> bool | None:
    if value is None:
        return None
    return value in {"1", "true", "True"}


def _excel_formula_literal(value: str | None) -> str:
    if value is None:
        return ""
    escaped = value.replace('"', '""')
    return f'"{escaped}"'


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
            target_mode = child.attrib.get("TargetMode")
            target = child.attrib.get("Target", "")
            if target_mode == "External":
                resolved_target = target
            else:
                resolved_target = _normalize_rel_target(name, target)
            rels[child.attrib["Id"]] = {
                "target": resolved_target,
                "type": child.attrib.get("Type", ""),
                "targetMode": target_mode,
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
            target_path = rel["target"]
            target_name = PurePosixPath(target_path).name
            target_parent = PurePosixPath(target_path).parent
            if str(target_parent) in {"", "."}:
                rels_path = f"_rels/{target_name}.rels"
            else:
                rels_path = f"{target_parent}/_rels/{target_name}.rels"
            sheet_type = "worksheet"
            if "/chartsheets/" in target_path:
                sheet_type = "chartsheet"
            elif "/dialogsheets/" in target_path:
                sheet_type = "dialogsheet"
            elif "/macrosheets/" in target_path:
                sheet_type = "macrosheet"
            sheets.append(
                {
                    "name": sheet.attrib.get("name", ""),
                    "sheetId": sheet.attrib.get("sheetId", ""),
                    "path": target_path,
                    "rels": self._read_relationships(rels_path),
                    "visibility": sheet.attrib.get("state", "visible"),
                    "sheetType": sheet_type,
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

    def parse_sheets(self) -> list[dict[str, Any]]:
        sheets: list[dict[str, Any]] = []
        for sheet in self.sheets:
            root = self._read_xml(sheet["path"])
            dimension = root.find("main:dimension", NS)
            table_count = 0
            table_parts = root.find("main:tableParts", NS)
            if table_parts is not None:
                table_count = len(table_parts.findall("main:tablePart", NS))
            sheets.append(
                {
                    "name": sheet["name"],
                    "sheetId": sheet["sheetId"],
                    "path": sheet["path"],
                    "sheetType": sheet.get("sheetType", "worksheet"),
                    "dimension": dimension.attrib.get("ref") if dimension is not None else None,
                    "tableCount": table_count,
                    "visibility": sheet.get("visibility", "visible"),
                }
            )
        return sheets

    def _count_defined_names(self) -> int:
        defined_names = self.workbook_xml.find("main:definedNames", NS)
        if defined_names is None:
            return 0
        count = 0
        for defined in defined_names.findall("main:definedName", NS):
            name = defined.attrib.get("name", "")
            if name.startswith("_xlnm."):
                continue
            count += 1
        return count

    def _count_power_query_inventory(self) -> dict[str, int]:
        try:
            connections_root = self._read_xml("xl/connections.xml")
        except KeyError:
            connection_count = 0
        else:
            connection_count = len(connections_root.findall("main:connection", NS))

        query_count = 0
        for name in self._zip.namelist():
            if not name.startswith("customXml/item") or not name.endswith(".xml"):
                continue
            try:
                root = self._read_xml(name)
            except ET.ParseError:
                continue
            if _local_name(root.tag) != "DataMashup":
                continue
            payload_text = "".join(root.itertext()).strip()
            if not payload_text:
                break
            try:
                payload_bytes = base64.b64decode(payload_text)
            except Exception:
                break
            zip_bytes = self._extract_embedded_zip_bytes(payload_bytes)
            if not zip_bytes:
                break
            try:
                with zipfile.ZipFile(io.BytesIO(zip_bytes)) as mashup_zip:
                    query_count = len(
                        [
                            item
                            for item in mashup_zip.namelist()
                            if item.lower().startswith("formulas/") and item.lower().endswith(".m")
                        ]
                    )
            except zipfile.BadZipFile:
                query_count = len(
                    [
                        item
                        for item in self._parse_local_zip_entries(zip_bytes)
                        if item.lower().startswith("formulas/") and item.lower().endswith(".m")
                    ]
                )
            break

        return {"queries": query_count, "connections": connection_count, "modelTables": 0}

    def build_inventory(self) -> dict[str, Any]:
        capability_matrix = _workbook_engine_capabilities(self.workbook_path)
        workbook = self.parse_workbook_metadata()
        sheets = self.parse_sheets()
        names_count = self._count_defined_names()
        pq_counts = self._count_power_query_inventory()
        workbook_protection = self.workbook_xml.find("main:workbookProtection", NS) is not None

        formulas_count = 0
        tables_count = 0
        data_validation_count = 0
        cf_count = 0
        hyperlinks_count = 0
        comments_count = 0
        pivots_count = 0
        charts_count = 0
        protected_sheets_count = 0
        supported_cf_types: set[str] = set()
        unsupported_cf_types: set[str] = set()

        for sheet in self.sheets:
            root = self._read_xml(sheet["path"])
            table_parts = root.find("main:tableParts", NS)
            if table_parts is not None:
                tables_count += len(table_parts.findall("main:tablePart", NS))

            sheet_data = root.find("main:sheetData", NS)
            if sheet_data is not None:
                for row in sheet_data.findall("main:row", NS):
                    for cell in row.findall("main:c", NS):
                        if cell.find("main:f", NS) is not None:
                            formulas_count += 1

            validations = root.find("main:dataValidations", NS)
            if validations is not None:
                data_validation_count += len(validations.findall("main:dataValidation", NS))

            if root.find("main:sheetProtection", NS) is not None:
                protected_sheets_count += 1

            hyperlinks_count += len(root.findall("main:hyperlinks/main:hyperlink", NS))

            for cf_group in root.findall("main:conditionalFormatting", NS):
                for rule in cf_group.findall("main:cfRule", NS):
                    cf_count += 1
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
                    if mapped_type in SUPPORTED_CF_TYPES:
                        supported_cf_types.add(mapped_type)
                    else:
                        unsupported_cf_types.add(mapped_type)

            pivots_count += len([rel for rel in sheet["rels"].values() if rel["type"].endswith("/pivotTable")])
            charts_count += len([rel for rel in sheet["rels"].values() if rel["type"].endswith("/chart")])

            comments_rel = next((rel for rel in sheet["rels"].values() if rel["type"].endswith("/comments")), None)
            if comments_rel is not None:
                try:
                    comments_root = self._read_xml(comments_rel["target"])
                except KeyError:
                    comments_root = None
                if comments_root is not None:
                    comments_count += len(comments_root.findall("main:commentList/main:comment", NS))

            if sheet.get("sheetType") == "chartsheet":
                charts_count += 1

        return {
            "workbookPath": str(self.workbook_path.resolve()),
            "backend": "package",
            "sourceFormat": self.workbook_path.suffix.lower(),
            "workingPath": str(self.workbook_path.resolve()),
            "normalization": "none",
            "warnings": [],
            "stagesTried": ["package"],
            "capabilities": {
                "excelCom": capability_matrix["desktop"]["available"],
                "packageReadable": True,
                "canRead": True,
                "canWrite": True,
                "writeBackend": "package",
                "refreshAwait": False,
                "powerQueryWrite": False,
                "vbaProjectAccess": False,
                "workbookReadOnly": None,
                "recommendedReadBackend": capability_matrix["recommendedReadBackend"],
                "recommendedWriteBackend": capability_matrix["recommendedWriteBackend"],
                "supportedReadSurfaces": capability_matrix["package"]["supportedReadSurfaces"],
                "writableSurfaces": capability_matrix["package"]["supportedWriteSurfaces"],
                "engines": capability_matrix,
            },
            "unsupported": [
                {"surface": "vba", "backend": "package", "reason": "Package backend cannot inspect live VBA components."},
                {"surface": "project", "backend": "package", "reason": "Package backend cannot inspect VBA project metadata."},
                {"surface": "references", "backend": "package", "reason": "Package backend cannot inspect VBA references."},
            ],
            "counts": {
                "workbook": 1,
                "sheets": len(sheets),
                "tables": tables_count,
                "names": names_count,
                "cf": cf_count,
                "pq": pq_counts["queries"],
                "connections": pq_counts["connections"],
                "modelTables": pq_counts["modelTables"],
                "vba": 0,
                "references": 0,
                "formulas": formulas_count,
                "dataValidation": data_validation_count,
                "charts": charts_count,
                "pivots": pivots_count,
                "hyperlinks": hyperlinks_count,
                "comments": comments_count,
                "dimensionSheets": len(sheets),
                "printSheets": len(sheets),
                "protectedSheets": protected_sheets_count,
                "workbookProtection": 1 if workbook_protection else 0,
            },
            "workbook": workbook,
            "sheets": sheets,
            "project": None,
            "supportedCfTypes": sorted(supported_cf_types),
            "unsupportedCfTypes": sorted(unsupported_cf_types),
        }

    def parse_workbook_metadata(self) -> dict[str, Any]:
        workbook_name = self.workbook_path.name
        metadata: dict[str, Any] = {
            "name": workbook_name,
            "path": str(self.workbook_path),
            "format": self.workbook_path.suffix.lower(),
            "packageReadable": True,
            "hasVbaProject": "xl/vbaProject.bin" in self._zip.namelist(),
            "hasExternalLinks": any(name.startswith("xl/externalLinks/") and name.endswith(".xml") for name in self._zip.namelist()),
            "packagePartCount": len(self._zip.namelist()),
            "calculation": {},
            "properties": {
                "core": {},
                "app": {},
                "custom": {},
            },
        }

        calc_pr = self.workbook_xml.find("main:calcPr", NS)
        if calc_pr is not None:
            metadata["calculation"] = {
                "mode": calc_pr.attrib.get("calcMode"),
                "calcCompleted": _parse_bool_attr(calc_pr.attrib.get("calcCompleted")),
                "calcOnSave": _parse_bool_attr(calc_pr.attrib.get("calcOnSave")),
                "fullCalcOnLoad": _parse_bool_attr(calc_pr.attrib.get("fullCalcOnLoad")),
                "forceFullCalc": _parse_bool_attr(calc_pr.attrib.get("forceFullCalc")),
                "iterate": _parse_bool_attr(calc_pr.attrib.get("iterate")),
                "iterateCount": calc_pr.attrib.get("iterateCount"),
                "iterateDelta": calc_pr.attrib.get("iterateDelta"),
                "refMode": calc_pr.attrib.get("refMode"),
            }

        def collect_simple_properties(root: ET.Element) -> dict[str, Any]:
            properties: dict[str, Any] = {}
            for child in list(root):
                key = _local_name(child.tag)
                text = "".join(child.itertext()).strip()
                properties[key] = text if text else dict(sorted(child.attrib.items()))
            return properties

        try:
            metadata["properties"]["core"] = collect_simple_properties(self._read_xml("docProps/core.xml"))
        except KeyError:
            metadata["properties"]["core"] = {}
        try:
            metadata["properties"]["app"] = collect_simple_properties(self._read_xml("docProps/app.xml"))
        except KeyError:
            metadata["properties"]["app"] = {}
        try:
            custom_root = self._read_xml("docProps/custom.xml")
        except KeyError:
            metadata["properties"]["custom"] = {}
        else:
            custom_properties: dict[str, Any] = {}
            for prop in list(custom_root):
                name = prop.attrib.get("name") or _local_name(prop.tag)
                value = ""
                if list(prop):
                    value = "".join(list(prop)[0].itertext()).strip()
                if not value:
                    value = "".join(prop.itertext()).strip()
                custom_properties[name] = value
            metadata["properties"]["custom"] = custom_properties
        return metadata

    def parse_dimensions(self) -> dict[str, Any]:
        sheet_dimensions: list[dict[str, Any]] = []
        for sheet in self.sheets:
            root = self._read_xml(sheet["path"])
            row_dimensions: list[dict[str, Any]] = []
            column_dimensions: list[dict[str, Any]] = []
            sheet_data = root.find("main:sheetData", NS)
            if sheet_data is not None:
                for row in sheet_data.findall("main:row", NS):
                    if not any(key in row.attrib for key in ("ht", "hidden", "outlineLevel", "collapsed", "customHeight", "s", "customFormat")):
                        continue
                    row_dimensions.append(
                        {
                            "row": int(row.attrib.get("r", "0") or "0"),
                            "height": float(row.attrib["ht"]) if "ht" in row.attrib else None,
                            "hidden": _parse_bool_attr(row.attrib.get("hidden")),
                            "outlineLevel": int(row.attrib["outlineLevel"]) if row.attrib.get("outlineLevel") else None,
                            "collapsed": _parse_bool_attr(row.attrib.get("collapsed")),
                            "style": int(row.attrib["s"]) if row.attrib.get("s") else None,
                            "customHeight": _parse_bool_attr(row.attrib.get("customHeight")),
                            "customFormat": _parse_bool_attr(row.attrib.get("customFormat")),
                        }
                    )
            cols = root.find("main:cols", NS)
            if cols is not None:
                for col in cols.findall("main:col", NS):
                    column_dimensions.append(
                        {
                            "min": int(col.attrib.get("min", "0") or "0"),
                            "max": int(col.attrib.get("max", "0") or "0"),
                            "width": float(col.attrib["width"]) if "width" in col.attrib else None,
                            "hidden": _parse_bool_attr(col.attrib.get("hidden")),
                            "bestFit": _parse_bool_attr(col.attrib.get("bestFit")),
                            "customWidth": _parse_bool_attr(col.attrib.get("customWidth")),
                            "style": int(col.attrib["style"]) if col.attrib.get("style") else None,
                            "outlineLevel": int(col.attrib["outlineLevel"]) if col.attrib.get("outlineLevel") else None,
                            "collapsed": _parse_bool_attr(col.attrib.get("collapsed")),
                        }
                    )
            sheet_dimensions.append(
                {
                    "sheet": sheet["name"],
                    "rows": row_dimensions,
                    "columns": column_dimensions,
                }
            )
        return {"sheets": sheet_dimensions}

    def parse_hyperlinks(self) -> list[dict[str, Any]]:
        hyperlinks: list[dict[str, Any]] = []
        for sheet in self.sheets:
            root = self._read_xml(sheet["path"])
            rels = sheet["rels"]
            for link in root.findall("main:hyperlinks/main:hyperlink", NS):
                rel_id = link.attrib.get(f"{{{NS['rel']}}}id")
                rel = rels.get(rel_id or "") if rel_id else None
                hyperlinks.append(
                    {
                        "sheet": sheet["name"],
                        "address": link.attrib.get("ref"),
                        "target": rel["target"] if rel else None,
                        "location": link.attrib.get("location"),
                        "display": link.attrib.get("display"),
                        "tooltip": link.attrib.get("tooltip"),
                    }
                )
        return sorted(hyperlinks, key=lambda entry: (entry["sheet"] or "", entry["address"] or ""))

    def parse_comments(self) -> list[dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        for sheet in self.sheets:
            comments_rel = next((rel for rel in sheet["rels"].values() if rel["type"].endswith("/comments")), None)
            if comments_rel is None:
                continue
            try:
                comments_root = self._read_xml(comments_rel["target"])
            except KeyError:
                continue
            authors = [author.text or "" for author in comments_root.findall("main:authors/main:author", NS)]
            for comment in comments_root.findall("main:commentList/main:comment", NS):
                author_id = comment.attrib.get("authorId")
                author = None
                if author_id and author_id.isdigit() and int(author_id) < len(authors):
                    author = authors[int(author_id)]
                text = "".join(node.text or "" for node in comment.iter() if _local_name(node.tag) == "t")
                comments.append(
                    {
                        "sheet": sheet["name"],
                        "address": comment.attrib.get("ref"),
                        "author": author,
                        "text": text,
                    }
                )
        return sorted(comments, key=lambda entry: (entry["sheet"] or "", entry["address"] or ""))

    def parse_print_settings(self) -> dict[str, Any]:
        print_areas: dict[str, str] = {}
        print_titles: dict[str, str] = {}
        defined_names = self.workbook_xml.find("main:definedNames", NS)
        if defined_names is not None:
            for item in defined_names.findall("main:definedName", NS):
                local_sheet_id = item.attrib.get("localSheetId")
                if local_sheet_id is None:
                    continue
                try:
                    sheet_name = self.sheets[int(local_sheet_id)]["name"]
                except (ValueError, IndexError):
                    continue
                name = item.attrib.get("name", "")
                if name == "_xlnm.Print_Area":
                    print_areas[sheet_name] = item.text or ""
                elif name == "_xlnm.Print_Titles":
                    print_titles[sheet_name] = item.text or ""

        sheets_payload: list[dict[str, Any]] = []
        for sheet in self.sheets:
            root = self._read_xml(sheet["path"])
            page_margins = root.find("main:pageMargins", NS)
            page_setup = root.find("main:pageSetup", NS)
            print_options = root.find("main:printOptions", NS)
            header_footer = root.find("main:headerFooter", NS)
            sheets_payload.append(
                {
                    "sheet": sheet["name"],
                    "printArea": print_areas.get(sheet["name"]),
                    "printTitles": print_titles.get(sheet["name"]),
                    "margins": None if page_margins is None else {
                        "left": page_margins.attrib.get("left"),
                        "right": page_margins.attrib.get("right"),
                        "top": page_margins.attrib.get("top"),
                        "bottom": page_margins.attrib.get("bottom"),
                        "header": page_margins.attrib.get("header"),
                        "footer": page_margins.attrib.get("footer"),
                    },
                    "pageSetup": None if page_setup is None else {
                        "paperSize": page_setup.attrib.get("paperSize"),
                        "scale": page_setup.attrib.get("scale"),
                        "fitToWidth": page_setup.attrib.get("fitToWidth"),
                        "fitToHeight": page_setup.attrib.get("fitToHeight"),
                        "orientation": page_setup.attrib.get("orientation"),
                        "usePrinterDefaults": _parse_bool_attr(page_setup.attrib.get("usePrinterDefaults")),
                        "blackAndWhite": _parse_bool_attr(page_setup.attrib.get("blackAndWhite")),
                        "draft": _parse_bool_attr(page_setup.attrib.get("draft")),
                    },
                    "printOptions": None if print_options is None else {
                        "horizontalCentered": _parse_bool_attr(print_options.attrib.get("horizontalCentered")),
                        "verticalCentered": _parse_bool_attr(print_options.attrib.get("verticalCentered")),
                        "headings": _parse_bool_attr(print_options.attrib.get("headings")),
                        "gridLines": _parse_bool_attr(print_options.attrib.get("gridLines")),
                    },
                    "headerFooter": None if header_footer is None else {
                        "oddHeader": header_footer.findtext("main:oddHeader", default="", namespaces=NS) or None,
                        "oddFooter": header_footer.findtext("main:oddFooter", default="", namespaces=NS) or None,
                        "evenHeader": header_footer.findtext("main:evenHeader", default="", namespaces=NS) or None,
                        "evenFooter": header_footer.findtext("main:evenFooter", default="", namespaces=NS) or None,
                        "firstHeader": header_footer.findtext("main:firstHeader", default="", namespaces=NS) or None,
                        "firstFooter": header_footer.findtext("main:firstFooter", default="", namespaces=NS) or None,
                    },
                }
            )
        return {"sheets": sheets_payload}

    def parse_styles(self) -> dict[str, Any]:
        parts: list[dict[str, Any]] = []
        for path in ("xl/styles.xml",):
            try:
                content = self._read_bytes(path)
            except KeyError:
                continue
            root = ET.fromstring(content)
            parts.append(
                {
                    "path": path,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "xml": content.decode("utf-8-sig"),
                    "counts": {
                        "numFmts": len(root.findall("main:numFmts/main:numFmt", NS)),
                        "fonts": len(root.findall("main:fonts/main:font", NS)),
                        "fills": len(root.findall("main:fills/main:fill", NS)),
                        "borders": len(root.findall("main:borders/main:border", NS)),
                        "cellXfs": len(root.findall("main:cellXfs/main:xf", NS)),
                        "cellStyles": len(root.findall("main:cellStyles/main:cellStyle", NS)),
                    },
                }
            )
        return {"parts": parts}

    def parse_themes(self) -> dict[str, Any]:
        parts: list[dict[str, Any]] = []
        for path in sorted(name for name in self._zip.namelist() if name.startswith("xl/theme/") and name.endswith(".xml")):
            content = self._read_bytes(path)
            root = ET.fromstring(content)
            parts.append(
                {
                    "path": path,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "name": root.attrib.get("name"),
                    "xml": content.decode("utf-8-sig"),
                }
            )
        return {"parts": parts}

    def get_cell_payload(self, sheet_name: str, cell_ref: str) -> dict[str, Any]:
        sheet_path = next((sheet["path"] for sheet in self.sheets if sheet["name"] == sheet_name), None)
        if sheet_path is None:
            raise ValueError(f"Unknown worksheet: {sheet_name}")
        row, col = _cell_ref_to_row_col(cell_ref.replace("$", ""))
        cells = self._read_sheet_cells(sheet_path)
        return {
            "sheet": sheet_name,
            "address": cell_ref.replace("$", "").upper(),
            "value": cells.get((row, col)),
        }

    def get_range_payload(self, sheet_name: str, range_ref: str) -> dict[str, Any]:
        sheet_path = next((sheet["path"] for sheet in self.sheets if sheet["name"] == sheet_name), None)
        if sheet_path is None:
            raise ValueError(f"Unknown worksheet: {sheet_name}")
        start_row, start_col, end_row, end_col = _range_ref_to_bounds(range_ref.replace("$", ""))
        cells = self._read_sheet_cells(sheet_path)
        values = []
        for row in range(start_row, end_row + 1):
            values.append([cells.get((row, col)) for col in range(start_col, end_col + 1)])
        return {
            "sheet": sheet_name,
            "range": range_ref.replace("$", "").upper(),
            "values": values,
        }

    def parse_formulas(self) -> list[dict[str, Any]]:
        formulas: list[dict[str, Any]] = []
        for sheet in self.sheets:
            root = self._read_xml(sheet["path"])
            sheet_data = root.find("main:sheetData", NS)
            if sheet_data is None:
                continue
            for row in sheet_data.findall("main:row", NS):
                for cell in row.findall("main:c", NS):
                    formula_node = cell.find("main:f", NS)
                    if formula_node is None:
                        continue
                    cell_ref = cell.attrib.get("r", "")
                    cell_type = cell.attrib.get("t")
                    style_id = None
                    if "s" in cell.attrib:
                        try:
                            style_id = int(cell.attrib["s"])
                        except ValueError:
                            style_id = None
                    value_node = cell.find("main:v", NS)
                    value = self._convert_scalar(value_node.text or "", cell_type, style_id) if value_node is not None else None
                    formulas.append(
                        {
                            "sheet": sheet["name"],
                            "address": cell_ref,
                            "formula": formula_node.text or "",
                            "value": value,
                            "kind": formula_node.attrib.get("t", "normal"),
                            "reference": formula_node.attrib.get("ref"),
                        }
                    )
        return sorted(formulas, key=lambda entry: (entry["sheet"], entry["address"]))

    def parse_data_validation(self) -> list[dict[str, Any]]:
        rules: list[dict[str, Any]] = []
        for sheet in self.sheets:
            root = self._read_xml(sheet["path"])
            validations = root.find("main:dataValidations", NS)
            if validations is None:
                continue
            for index, validation in enumerate(validations.findall("main:dataValidation", NS), start=1):
                rules.append(
                    {
                        "id": f"DV-{sheet['name']}-{index:03d}",
                        "sheet": sheet["name"],
                        "address": (validation.attrib.get("sqref", "") or "").replace(" ", ","),
                        "type": validation.attrib.get("type", "any"),
                        "operator": validation.attrib.get("operator"),
                        "allowBlank": _parse_bool_attr(validation.attrib.get("allowBlank")),
                        "showInputMessage": _parse_bool_attr(validation.attrib.get("showInputMessage")),
                        "showErrorMessage": _parse_bool_attr(validation.attrib.get("showErrorMessage")),
                        "errorStyle": validation.attrib.get("errorStyle"),
                        "formula1": (validation.findtext("main:formula1", default="", namespaces=NS) or None),
                        "formula2": (validation.findtext("main:formula2", default="", namespaces=NS) or None),
                    }
                )
        return sorted(rules, key=lambda entry: (entry["sheet"], entry["address"], entry["id"]))

    def parse_protection(self) -> dict[str, Any]:
        workbook_protection = None
        workbook_node = self.workbook_xml.find("main:workbookProtection", NS)
        if workbook_node is not None:
            workbook_protection = {
                "lockStructure": _parse_bool_attr(workbook_node.attrib.get("lockStructure")),
                "lockWindows": _parse_bool_attr(workbook_node.attrib.get("lockWindows")),
                "lockRevision": _parse_bool_attr(workbook_node.attrib.get("lockRevision")),
            }

        worksheets: list[dict[str, Any]] = []
        for sheet in self.sheets:
            root = self._read_xml(sheet["path"])
            protection_node = root.find("main:sheetProtection", NS)
            if protection_node is None:
                continue
            worksheets.append(
                {
                    "sheet": sheet["name"],
                    "enabled": _parse_bool_attr(protection_node.attrib.get("sheet")),
                    "objects": _parse_bool_attr(protection_node.attrib.get("objects")),
                    "scenarios": _parse_bool_attr(protection_node.attrib.get("scenarios")),
                    "formatCells": _parse_bool_attr(protection_node.attrib.get("formatCells")),
                    "formatColumns": _parse_bool_attr(protection_node.attrib.get("formatColumns")),
                    "formatRows": _parse_bool_attr(protection_node.attrib.get("formatRows")),
                    "insertColumns": _parse_bool_attr(protection_node.attrib.get("insertColumns")),
                    "insertRows": _parse_bool_attr(protection_node.attrib.get("insertRows")),
                    "insertHyperlinks": _parse_bool_attr(protection_node.attrib.get("insertHyperlinks")),
                    "deleteColumns": _parse_bool_attr(protection_node.attrib.get("deleteColumns")),
                    "deleteRows": _parse_bool_attr(protection_node.attrib.get("deleteRows")),
                    "selectLockedCells": _parse_bool_attr(protection_node.attrib.get("selectLockedCells")),
                    "sort": _parse_bool_attr(protection_node.attrib.get("sort")),
                    "autoFilter": _parse_bool_attr(protection_node.attrib.get("autoFilter")),
                    "pivotTables": _parse_bool_attr(protection_node.attrib.get("pivotTables")),
                    "selectUnlockedCells": _parse_bool_attr(protection_node.attrib.get("selectUnlockedCells")),
                }
            )
        return {
            "workbook": workbook_protection,
            "worksheets": sorted(worksheets, key=lambda entry: entry["sheet"]),
        }

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

    def _drawing_relationships_path(self, drawing_path: str) -> str:
        drawing_name = PurePosixPath(drawing_path).name
        drawing_parent = PurePosixPath(drawing_path).parent
        if str(drawing_parent) in {"", "."}:
            return f"_rels/{drawing_name}.rels"
        return f"{drawing_parent}/_rels/{drawing_name}.rels"

    def _chart_title_text(self, chart_root: ET.Element) -> str | None:
        title_node = chart_root.find("c:chart/c:title", NS)
        if title_node is None:
            return None
        rich_text = [node.text or "" for node in title_node.findall(".//a:t", NS)]
        if rich_text:
            return "".join(rich_text)
        value_text = [node.text or "" for node in title_node.findall(".//c:v", NS)]
        if value_text:
            return "".join(value_text)
        return None

    def _chart_series_name_expression(self, series_node: ET.Element) -> tuple[str | None, str | None]:
        tx_node = series_node.find("c:tx", NS)
        if tx_node is None:
            return None, None
        formula = tx_node.findtext(".//c:f", default="", namespaces=NS) or None
        literal = tx_node.findtext(".//c:v", default="", namespaces=NS) or None
        if literal is None:
            literal = "".join(node.text or "" for node in tx_node.findall(".//a:t", NS)) or None
        expression = formula if formula else (_excel_formula_literal(literal) if literal else None)
        return literal or formula, expression

    def _chart_series_axis_expression(self, series_node: ET.Element, *axis_names: str) -> str | None:
        for axis_name in axis_names:
            axis_node = series_node.find(f"c:{axis_name}", NS)
            if axis_node is None:
                continue
            formula = axis_node.findtext(".//c:f", default="", namespaces=NS) or None
            if formula:
                return formula
            literal_values = [node.text or "" for node in axis_node.findall(".//c:v", NS)]
            if literal_values:
                return "{" + ",".join(_excel_formula_literal(item) for item in literal_values) + "}"
        return None

    def _chart_type_name(self, chart_root: ET.Element) -> str | None:
        plot_area = chart_root.find("c:chart/c:plotArea", NS)
        if plot_area is None:
            return None
        for child in list(plot_area):
            local_name = _local_name(child.tag)
            if local_name.endswith("Chart"):
                return local_name
        return None

    def _chart_series_payload(self, chart_root: ET.Element) -> list[dict[str, Any]]:
        series_payload: list[dict[str, Any]] = []
        for series_node in chart_root.findall(".//c:ser", NS):
            name, name_expr = self._chart_series_name_expression(series_node)
            categories_expr = self._chart_series_axis_expression(series_node, "cat", "xVal")
            values_expr = self._chart_series_axis_expression(series_node, "val", "yVal")
            bubble_expr = self._chart_series_axis_expression(series_node, "bubbleSize")
            order = series_node.find("c:order", NS)
            order_value = order.attrib.get("val") if order is not None else ""
            formula_parts = [
                name_expr or "",
                categories_expr or "",
                values_expr or bubble_expr or "",
                order_value,
            ]
            formula = None
            if any(part != "" for part in formula_parts):
                formula = "=SERIES(" + ",".join(formula_parts) + ")"
            series_payload.append(
                {
                    "name": name,
                    "nameFormula": name_expr,
                    "categoriesFormula": categories_expr,
                    "valuesFormula": values_expr,
                    "bubbleSizeFormula": bubble_expr,
                    "order": order_value,
                    "formula": formula,
                }
            )
        return series_payload

    def _embedded_chart_address(self, anchor_node: ET.Element) -> str | None:
        from_node = anchor_node.find("xdr:from", NS)
        to_node = anchor_node.find("xdr:to", NS)
        if from_node is None or to_node is None:
            return None
        try:
            start_col = int(from_node.findtext("xdr:col", default="0", namespaces=NS)) + 1
            start_row = int(from_node.findtext("xdr:row", default="0", namespaces=NS)) + 1
            end_col = int(to_node.findtext("xdr:col", default="0", namespaces=NS)) + 1
            end_row = int(to_node.findtext("xdr:row", default="0", namespaces=NS)) + 1
        except ValueError:
            return None
        return f"{_row_col_to_cell_ref(start_row, start_col)}:{_row_col_to_cell_ref(end_row, end_col)}"

    def _chart_entry_from_part(
        self,
        chart_path: str,
        *,
        kind: str,
        sheet_name: str,
        name: str | None,
        address: str | None,
    ) -> dict[str, Any]:
        chart_root = self._read_xml(chart_path)
        title = self._chart_title_text(chart_root)
        series = self._chart_series_payload(chart_root)
        return {
            "name": name,
            "kind": kind,
            "sheet": sheet_name,
            "address": address,
            "chartType": self._chart_type_name(chart_root),
            "hasTitle": title is not None,
            "title": title,
            "series": series,
        }

    def parse_charts(self) -> list[dict[str, Any]]:
        charts: list[dict[str, Any]] = []
        for sheet in self.sheets:
            if sheet.get("sheetType") == "worksheet":
                for rel in sheet["rels"].values():
                    if not rel["type"].endswith("/drawing"):
                        continue
                    drawing_path = rel["target"]
                    drawing_root = self._read_xml(drawing_path)
                    drawing_rels = self._read_relationships(self._drawing_relationships_path(drawing_path))
                    for anchor_node in drawing_root.findall("xdr:twoCellAnchor", NS):
                        chart_node = anchor_node.find("xdr:graphicFrame/a:graphic/a:graphicData/c:chart", NS)
                        if chart_node is None:
                            continue
                        chart_rel_id = chart_node.attrib.get(f"{{{NS['rel']}}}id")
                        chart_rel = drawing_rels.get(chart_rel_id or "")
                        if not chart_rel:
                            continue
                        c_nv_pr = anchor_node.find("xdr:graphicFrame/xdr:nvGraphicFramePr/xdr:cNvPr", NS)
                        name = c_nv_pr.attrib.get("name") if c_nv_pr is not None else None
                        charts.append(
                            self._chart_entry_from_part(
                                chart_rel["target"],
                                kind="embedded",
                                sheet_name=sheet["name"],
                                name=name,
                                address=self._embedded_chart_address(anchor_node),
                            )
                        )
            elif sheet.get("sheetType") == "chartsheet":
                root = self._read_xml(sheet["path"])
                drawing_node = root.find("main:drawing", NS)
                if drawing_node is None:
                    continue
                drawing_rel_id = drawing_node.attrib.get(f"{{{NS['rel']}}}id")
                drawing_rel = sheet["rels"].get(drawing_rel_id or "")
                if not drawing_rel:
                    continue
                drawing_path = drawing_rel["target"]
                drawing_root = self._read_xml(drawing_path)
                drawing_rels = self._read_relationships(self._drawing_relationships_path(drawing_path))
                chart_rel = next((rel for rel in drawing_rels.values() if rel["type"].endswith("/chart")), None)
                if chart_rel is None:
                    chart_node = drawing_root.find(".//c:chart", NS)
                    if chart_node is not None:
                        chart_rel_id = chart_node.attrib.get(f"{{{NS['rel']}}}id")
                        chart_rel = drawing_rels.get(chart_rel_id or "")
                if chart_rel is None:
                    continue
                charts.append(
                    self._chart_entry_from_part(
                        chart_rel["target"],
                        kind="chart-sheet",
                        sheet_name=sheet["name"],
                        name=sheet["name"],
                        address=None,
                    )
                )
        return sorted(charts, key=lambda entry: ((entry["kind"] or ""), (entry["sheet"] or ""), (entry["name"] or "")))

    def parse_pivots(self) -> list[dict[str, Any]]:
        workbook_pivot_caches: dict[str, str] = {}
        pivot_caches = self.workbook_xml.find("main:pivotCaches", NS)
        if pivot_caches is not None:
            for pivot_cache in pivot_caches.findall("main:pivotCache", NS):
                cache_id = pivot_cache.attrib.get("cacheId")
                rel_id = pivot_cache.attrib.get(f"{{{NS['rel']}}}id")
                rel = self.workbook_rels.get(rel_id or "")
                if cache_id and rel:
                    workbook_pivot_caches[cache_id] = rel["target"]

        pivot_entries: list[dict[str, Any]] = []
        for sheet in self.sheets:
            for rel in sheet["rels"].values():
                if not rel["type"].endswith("/pivotTable"):
                    continue
                pivot_xml = self._read_xml(rel["target"])
                location = pivot_xml.find("main:location", NS)
                cache_id = pivot_xml.attrib.get("cacheId")
                cache_path = workbook_pivot_caches.get(cache_id or "")
                cache_source: dict[str, Any] | None = None
                if cache_path:
                    try:
                        cache_xml = self._read_xml(cache_path)
                    except KeyError:
                        cache_xml = None
                    if cache_xml is not None:
                        worksheet_source = cache_xml.find("main:cacheSource/main:worksheetSource", NS)
                        if worksheet_source is not None:
                            cache_source = {
                                "sheet": worksheet_source.attrib.get("sheet"),
                                "ref": worksheet_source.attrib.get("ref"),
                                "name": worksheet_source.attrib.get("name"),
                            }
                pivot_entries.append(
                    {
                        "sheet": sheet["name"],
                        "name": pivot_xml.attrib.get("name", PurePosixPath(rel["target"]).stem),
                        "cacheId": cache_id,
                        "location": location.attrib.get("ref") if location is not None else None,
                        "dataCaption": pivot_xml.attrib.get("dataCaption"),
                        "cacheSource": cache_source,
                    }
                )
        return sorted(pivot_entries, key=lambda entry: (entry["sheet"], entry["name"]))

    def parse_names(self) -> list[dict[str, Any]]:
        names = []
        defined_names = self.workbook_xml.find("main:definedNames", NS)
        if defined_names is None:
            return names
        for defined in defined_names.findall("main:definedName", NS):
            name = defined.attrib.get("name", "")
            if name.startswith("_xlnm."):
                continue
            names.append(
                {
                    "name": name,
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
        "workbook-metadata": "workbook",
        "workbook_metadata": "workbook",
        "metadata": "workbook",
        "conditional-formatting": "cf",
        "conditional_formatting": "cf",
        "power-query": "pq",
        "power_query": "pq",
        "data_validation": "data-validation",
        "datavalidation": "data-validation",
        "comments-notes": "comments",
        "comments_notes": "comments",
        "notes": "comments",
        "links": "hyperlinks",
        "page-layout": "print",
        "page_layout": "print",
        "layout": "print",
        "row-column-dimensions": "dimensions",
        "row_column_dimensions": "dimensions",
    }
    normalized = []
    for item in surface_text.split(","):
        token = item.strip().lower()
        if not token:
            continue
        normalized.append(aliases.get(token, token))
    return normalized


PACKAGE_READABLE_EXTENSIONS = {".xlsx", ".xlsm", ".xltx", ".xltm", ".xlam"}
DESKTOP_EXTENSIONS = {".xls", ".xlsx", ".xlsm", ".xlsb", ".xlt", ".xltx", ".xltm", ".xlam", ".ods", ".csv", ".txt"}
PACKAGE_WRITABLE_SURFACES = [
    "workbook",
    "sheets",
    "tables",
    "names",
    "formulas",
    "data-validation",
    "cf",
    "protection",
    "dimensions",
    "hyperlinks",
    "comments",
    "print",
    "charts",
    "styles",
    "themes",
]
PACKAGE_DESKTOP_WRITE_SURFACES = ["pivots", "slicers", "timelines", "pq", "connections", "model"]
PACKAGE_PARTIAL_WRITE_SURFACES = ["charts"]
ARTIFACT_AUTHORING_SURFACES = ["workbook-author", "dashboard-author", "csv-author", "preview-render"]

def _load_capability_matrix() -> dict[str, Any]:
    with CAPABILITY_MATRIX_PATH.open("r", encoding="utf-8") as handle:
        matrix = json.load(handle)
    surfaces = matrix.get("surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        raise ValueError(f"Capability matrix has no surfaces: {CAPABILITY_MATRIX_PATH}")
    return matrix


CAPABILITY_MATRIX = _load_capability_matrix()
CAPABILITY_LEDGER: dict[str, dict[str, Any]] = {
    surface["id"]: {
        "category": surface["category"],
        "read": surface["readLane"],
        "write": surface["writeLane"],
        "verify": surface["verify"],
        "risk": surface["risk"],
        "supportLevel": surface["supportLevel"],
        "route": surface["route"],
        "operations": surface["operations"],
        "hostRequirements": surface.get("hostRequirements", []),
        "secretPolicy": surface.get("secretPolicy"),
        "destructiveRisk": surface.get("destructiveRisk"),
        "evidenceSelectors": surface.get("evidenceSelectors", []),
    }
    for surface in CAPABILITY_MATRIX["surfaces"]
}


def _surface_route_payload(surface: str) -> dict[str, Any]:
    ledger_entry = CAPABILITY_LEDGER.get(surface, {})
    if surface in PACKAGE_DESKTOP_WRITE_SURFACES:
        payload = {
            "surface": surface,
            "readBackend": "package",
            "writeBackend": "desktop",
            "route": "desktop-write",
            "requiresBackend": "desktop",
            "canReadPackage": True,
            "canWritePackage": False,
            "canWriteDesktop": True,
            "preservation": "package-inventory/desktop-mutation",
            "platformLimits": [
                "Windows desktop Excel is required for fidelity-preserving writes on this surface.",
                "Package mode inventories metadata and dependencies but does not rewrite this artifact.",
            ],
        }
        payload.update({"category": ledger_entry.get("category"), "verify": ledger_entry.get("verify"), "risk": ledger_entry.get("risk")})
        return payload
    if surface in PACKAGE_PARTIAL_WRITE_SURFACES:
        payload = {
            "surface": surface,
            "readBackend": "package",
            "writeBackend": "desktop-preferred",
            "route": "partial-package-write",
            "requiresBackend": None,
            "canReadPackage": True,
            "canWritePackage": True,
            "canWriteDesktop": True,
            "preservation": "relationship-aware inventory; desktop recommended for rich edits",
            "platformLimits": [
                "Package mode preserves and inventories chart relationships; rich chart authoring is routed to desktop Excel.",
            ],
        }
        payload.update({"category": ledger_entry.get("category"), "verify": ledger_entry.get("verify"), "risk": ledger_entry.get("risk")})
        return payload
    payload = {
        "surface": surface,
        "readBackend": "package",
        "writeBackend": "package",
        "route": "package-read-write",
        "requiresBackend": None,
        "canReadPackage": True,
        "canWritePackage": surface in PACKAGE_WRITABLE_SURFACES,
        "canWriteDesktop": True,
        "preservation": "package-roundtrip-safe",
        "platformLimits": [],
    }
    payload.update({"category": ledger_entry.get("category"), "verify": ledger_entry.get("verify"), "risk": ledger_entry.get("risk")})
    return payload


def _capability_ledger_for_workbook(workbook_path: Path) -> dict[str, Any]:
    engine_capabilities = _workbook_engine_capabilities(workbook_path)
    extension = workbook_path.suffix.lower()
    package_readable = extension in PACKAGE_READABLE_EXTENSIONS
    desktop_available = extension in DESKTOP_EXTENSIONS
    surfaces: dict[str, Any] = {}
    for surface, spec in sorted(CAPABILITY_LEDGER.items()):
        read_lane = spec["read"]
        write_lane = spec["write"]
        read_available = (
            (read_lane == "package" and package_readable)
            or (read_lane == "desktop" and desktop_available)
            or read_lane == "automation"
        )
        write_available = (
            (write_lane == "package" and package_readable)
            or (write_lane == "desktop" and desktop_available)
            or (write_lane == "desktop-preferred" and (package_readable or desktop_available))
            or write_lane in {"automation", "preserve-only"}
        )
        route = {
            "package": "package-write",
            "desktop": "desktop-write",
            "desktop-preferred": "partial-package-write",
            "automation": "automation-write",
            "graph": "graph-write",
            "tom-fabric": "tom-fabric-write",
            "preserve-only": "preserve-only",
        }.get(write_lane, "platform-impossible")
        surfaces[surface] = {
            "surface": surface,
            "category": spec["category"],
            "readLane": read_lane,
            "writeLane": write_lane,
            "route": route,
            "canReadHere": read_available,
            "canWriteHere": write_available and write_lane != "preserve-only",
            "canPreserveHere": package_readable or desktop_available,
            "verify": spec["verify"],
            "risk": spec["risk"],
            "supportLevel": spec.get("supportLevel"),
            "operations": spec.get("operations", []),
            "hostRequirements": spec.get("hostRequirements", []),
            "secretPolicy": spec.get("secretPolicy"),
            "destructiveRisk": spec.get("destructiveRisk"),
            "requires": {
                "package": [],
                "desktop-preferred": [],
                "automation": [],
                "preserve-only": [],
                "desktop": ["desktop-excel"],
                "graph": ["microsoft-graph-workbook-session"],
                "tom-fabric": ["xmla-or-fabric-workspace"],
            }.get(write_lane, ["unknown-host"]),
        }
    return {
        "version": 1,
        "sourceFormat": extension,
        "engines": engine_capabilities,
        "surfaces": surfaces,
        "counts": {
            "surfaces": len(surfaces),
            "packageWrite": sum(1 for item in surfaces.values() if item["route"] == "package-write"),
            "desktopWrite": sum(1 for item in surfaces.values() if item["route"] == "desktop-write"),
            "automationWrite": sum(1 for item in surfaces.values() if item["route"] == "automation-write"),
            "preserveOnly": sum(1 for item in surfaces.values() if item["route"] == "preserve-only"),
        },
    }


def _workbook_engine_capabilities(workbook_path: Path) -> dict[str, Any]:
    extension = workbook_path.suffix.lower()
    package_readable = extension in PACKAGE_READABLE_EXTENSIONS
    desktop_recommended = extension in {".xls", ".xlsb", ".ods", ".csv", ".txt"}
    desktop_required_surfaces = [
        "charts",
        "pivots",
        "pq-write",
        "connections-write",
        "model-write",
        "comments-threaded",
        "print-export",
        "repair",
        "compatibility-check",
        "document-inspector",
        "convert",
    ]
    return {
        "sourceFormat": extension,
        "recommendedReadBackend": "desktop" if desktop_recommended else "package",
        "recommendedWriteBackend": "desktop" if desktop_recommended else "package",
        "package": {
            "available": package_readable,
            "canRead": package_readable,
            "canWrite": package_readable,
        "supportedReadSurfaces": [
                "workbook",
                "sheets",
                "tables",
                "names",
                "formulas",
                "data-validation",
                "protection",
                "cf",
                "charts",
                "pivots",
                "pq",
                "connections",
                "model",
                "hyperlinks",
                "comments",
                "print",
                "dimensions",
                "styles",
                "themes",
            ] if package_readable else [],
            "supportedWriteSurfaces": PACKAGE_WRITABLE_SURFACES if package_readable else [],
        },
        "desktop": {
            "available": extension in DESKTOP_EXTENSIONS,
            "canRead": extension in DESKTOP_EXTENSIONS,
            "canWrite": extension in DESKTOP_EXTENSIONS,
            "requiredFor": desktop_required_surfaces if extension in DESKTOP_EXTENSIONS else [],
        },
        "artifact": {
            "available": True,
            "canGenerate": True,
            "surfaces": ARTIFACT_AUTHORING_SURFACES,
            "recommendedFor": [
                "new-workbook-authoring",
                "polished-dashboard-generation",
                "rendered-preview-validation",
                "csv-to-xlsx-generation",
            ],
        },
        "automation": {
            "available": True,
            "canGenerate": True,
            "surfaces": ["vba", "office-scripts", "excel-js-api", "office-addin"],
        },
    }


def build_query_payload(workbook_path: Path, surfaces: list[str]) -> dict[str, Any]:
    package = WorkbookPackage(workbook_path)
    try:
        capability_matrix = _workbook_engine_capabilities(workbook_path)
        payload: dict[str, Any] = {
            "workbookPath": str(workbook_path.resolve()),
            "backend": "package",
            "sourceFormat": workbook_path.suffix.lower(),
            "workingPath": str(workbook_path.resolve()),
            "normalization": "none",
            "warnings": [],
            "stagesTried": ["package"],
            "capabilities": {
                "excelCom": capability_matrix["desktop"]["available"],
                "packageReadable": True,
                "canRead": True,
                "canWrite": True,
                "writeBackend": "package",
                "refreshAwait": False,
                "powerQueryWrite": False,
                "vbaProjectAccess": False,
                "workbookReadOnly": None,
                "recommendedReadBackend": capability_matrix["recommendedReadBackend"],
                "recommendedWriteBackend": capability_matrix["recommendedWriteBackend"],
                "supportedReadSurfaces": capability_matrix["package"]["supportedReadSurfaces"],
                "writableSurfaces": capability_matrix["package"]["supportedWriteSurfaces"],
                "engines": capability_matrix,
            },
            "unsupported": [],
            "engineRoutes": {
                surface: _surface_route_payload(surface) for surface in PACKAGE_SURFACE_SPECS
            },
        }
        if not surfaces or "workbook" in surfaces:
            payload["workbook"] = package.parse_workbook_metadata()
        if not surfaces or "sheets" in surfaces:
            payload["sheets"] = package.parse_sheets()
        if not surfaces or "tables" in surfaces:
            payload["tables"] = package.parse_tables()
        if not surfaces or "names" in surfaces:
            payload["names"] = package.parse_names()
        if not surfaces or "formulas" in surfaces:
            payload["formulas"] = package.parse_formulas()
        if not surfaces or "data-validation" in surfaces:
            payload["dataValidation"] = package.parse_data_validation()
        if not surfaces or "protection" in surfaces:
            payload["protection"] = package.parse_protection()
        if not surfaces or "charts" in surfaces:
            payload["charts"] = package.parse_charts()
        if not surfaces or "pivots" in surfaces:
            payload["pivots"] = package.parse_pivots()
        if not surfaces or "dimensions" in surfaces:
            payload["dimensions"] = package.parse_dimensions()
        if not surfaces or "hyperlinks" in surfaces:
            payload["hyperlinks"] = package.parse_hyperlinks()
        if not surfaces or "comments" in surfaces:
            payload["comments"] = package.parse_comments()
        if not surfaces or "print" in surfaces:
            payload["print"] = package.parse_print_settings()
        if not surfaces or "styles" in surfaces:
            payload["styles"] = package.parse_styles()
        if not surfaces or "themes" in surfaces:
            payload["themes"] = package.parse_themes()
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
        requested_surfaces = set(surfaces) if surfaces else {
            "sheets",
            "tables",
            "names",
            "cf",
            "pq",
            "connections",
            "model",
            "formulas",
            "data-validation",
            "protection",
            "charts",
            "pivots",
            "workbook",
            "dimensions",
            "hyperlinks",
            "comments",
            "print",
            "styles",
            "themes",
            "vba",
            "project",
            "references",
        }
        for surface, reason in (
            ("vba", "Package backend cannot inspect live VBA components."),
            ("project", "Package backend cannot inspect VBA project metadata."),
            ("references", "Package backend cannot inspect VBA references."),
        ):
            if surface in requested_surfaces:
                payload["unsupported"].append({"surface": surface, "backend": "package", "reason": reason})
        return payload
    finally:
        package.close()


def build_inventory_payload(workbook_path: Path) -> dict[str, Any]:
    package = WorkbookPackage(workbook_path)
    try:
        return package.build_inventory()
    finally:
        package.close()


def build_inspection_payload(query_payload: dict[str, Any]) -> dict[str, Any]:
    cf = query_payload.get("cf", [])
    model = query_payload.get("model", {}) or {}
    protection = query_payload.get("protection") or {}
    inspection = {
        "workbookPath": query_payload["workbookPath"],
        "backend": query_payload["backend"],
        "sourceFormat": query_payload["sourceFormat"],
        "workingPath": query_payload["workingPath"],
        "normalization": query_payload["normalization"],
        "warnings": query_payload.get("warnings", []),
        "stagesTried": query_payload.get("stagesTried", []),
        "capabilities": query_payload.get("capabilities", {}),
        "unsupported": query_payload.get("unsupported", []),
        "counts": {
            "workbook": 1 if query_payload.get("workbook") else 0,
            "sheets": len(query_payload.get("sheets", [])),
            "tables": len(query_payload.get("tables", [])),
            "names": len(query_payload.get("names", [])),
            "cf": len(cf),
            "pq": len(query_payload.get("pq", [])),
            "connections": len(query_payload.get("connections", [])),
            "modelTables": len(model.get("modelTables", [])),
            "vba": len(query_payload.get("vba", [])),
            "references": len(query_payload.get("references", [])),
            "formulas": len(query_payload.get("formulas", [])),
            "dataValidation": len(query_payload.get("dataValidation", [])),
            "charts": len(query_payload.get("charts", [])),
            "pivots": len(query_payload.get("pivots", [])),
            "hyperlinks": len(query_payload.get("hyperlinks", [])),
            "comments": len(query_payload.get("comments", [])),
            "dimensionSheets": len((query_payload.get("dimensions") or {}).get("sheets", [])),
            "printSheets": len((query_payload.get("print") or {}).get("sheets", [])),
            "protectedSheets": len(protection.get("worksheets", [])),
            "workbookProtection": 1 if protection.get("workbook") else 0,
        },
        "workbook": query_payload.get("workbook"),
        "project": query_payload.get("project"),
        "supportedCfTypes": sorted({rule["type"] for rule in cf if rule.get("supported")}),
        "unsupportedCfTypes": sorted({rule["type"] for rule in cf if not rule.get("supported")}),
    }
    return inspection


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _rewrite_workbook_package(workbook_path: Path, updates: dict[str, bytes], deletes: set[str] | None = None) -> None:
    workbook_path = workbook_path.resolve()
    delete_names = deletes or set()
    with zipfile.ZipFile(workbook_path, "r") as source:
        members = {name: source.read(name) for name in source.namelist() if name not in delete_names}
    members.update(updates)
    fd, temp_name = tempfile.mkstemp(prefix="excel-foundry-", suffix=workbook_path.suffix, dir=str(workbook_path.parent))
    os.close(fd)
    Path(temp_name).unlink(missing_ok=True)
    temp_path = Path(temp_name)
    try:
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as target:
            for name, payload in members.items():
                target.writestr(name, payload)
        temp_path.replace(workbook_path)
    finally:
        temp_path.unlink(missing_ok=True)


def _relative_or_absolute(base_dir: Path, target_path: Path) -> str:
    try:
        return os.path.relpath(str(target_path.resolve()), str(base_dir.resolve())).replace("\\", "/")
    except Exception:
        return str(target_path.resolve())


def bootstrap_bundle(workbook_path: Path, output_dir: Path, manifest_path: Path | None, surfaces: list[str]) -> dict[str, Any]:
    query_payload = build_query_payload(workbook_path, surfaces)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_path or output_dir / "excel-sync.manifest.json"
    structure_dir = output_dir / "workbook_structure"
    _write_json(structure_dir / "workbook.json", {"workbook": query_payload.get("workbook", {})})
    _write_json(structure_dir / "sheets.json", {"sheets": query_payload.get("sheets", [])})
    _write_json(structure_dir / "tables.json", {"tables": query_payload.get("tables", [])})
    _write_json(structure_dir / "names.json", {"names": query_payload.get("names", [])})
    _write_json(structure_dir / "conditional_formatting.json", {"rules": query_payload.get("cf", [])})
    _write_json(structure_dir / "formulas.json", {"formulas": query_payload.get("formulas", [])})
    _write_json(structure_dir / "data_validation.json", {"rules": query_payload.get("dataValidation", [])})
    _write_json(structure_dir / "protection.json", query_payload.get("protection", {"workbook": None, "worksheets": []}))
    _write_json(structure_dir / "charts.json", {"charts": query_payload.get("charts", [])})
    _write_json(structure_dir / "pivots.json", {"pivots": query_payload.get("pivots", [])})
    _write_json(structure_dir / "dimensions.json", query_payload.get("dimensions", {"sheets": []}))
    _write_json(structure_dir / "hyperlinks.json", {"hyperlinks": query_payload.get("hyperlinks", [])})
    _write_json(structure_dir / "comments.json", {"comments": query_payload.get("comments", [])})
    _write_json(structure_dir / "print.json", query_payload.get("print", {"sheets": []}))
    _write_json(structure_dir / "styles.json", query_payload.get("styles", {"parts": []}))
    _write_json(structure_dir / "themes.json", query_payload.get("themes", {"parts": []}))
    manifest: dict[str, Any] = {
        "version": 2,
        "workbookPath": _relative_or_absolute(manifest_path.parent, workbook_path),
        "vbaComponents": [],
        "structure": {
            "workbookPath": str(PurePosixPath("workbook_structure/workbook.json")),
            "sheetsPath": str(PurePosixPath("workbook_structure/sheets.json")),
            "tablesPath": str(PurePosixPath("workbook_structure/tables.json")),
            "namesPath": str(PurePosixPath("workbook_structure/names.json")),
            "conditionalFormattingPath": str(PurePosixPath("workbook_structure/conditional_formatting.json")),
            "formulasPath": str(PurePosixPath("workbook_structure/formulas.json")),
            "dataValidationPath": str(PurePosixPath("workbook_structure/data_validation.json")),
            "protectionPath": str(PurePosixPath("workbook_structure/protection.json")),
            "chartsPath": str(PurePosixPath("workbook_structure/charts.json")),
            "pivotsPath": str(PurePosixPath("workbook_structure/pivots.json")),
            "dimensionsPath": str(PurePosixPath("workbook_structure/dimensions.json")),
            "hyperlinksPath": str(PurePosixPath("workbook_structure/hyperlinks.json")),
            "commentsPath": str(PurePosixPath("workbook_structure/comments.json")),
            "printPath": str(PurePosixPath("workbook_structure/print.json")),
            "stylesPath": str(PurePosixPath("workbook_structure/styles.json")),
            "themesPath": str(PurePosixPath("workbook_structure/themes.json")),
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
        "capabilities": query_payload.get("capabilities", {}),
        "unsupported": query_payload.get("unsupported", []),
    }


PACKAGE_SURFACE_SPECS: dict[str, dict[str, Any]] = {
    "workbook": {
        "queryKey": "workbook",
        "artifactPath": ("structure", "workbookPath"),
        "artifactKey": "workbook",
        "writable": True,
        "selectorKinds": set(),
        "keyFields": (),
    },
    "sheets": {
        "queryKey": "sheets",
        "artifactPath": ("structure", "sheetsPath"),
        "artifactKey": "sheets",
        "writable": True,
        "selectorKinds": {"sheet"},
        "keyFields": ("name",),
    },
    "tables": {
        "queryKey": "tables",
        "artifactPath": ("structure", "tablesPath"),
        "artifactKey": "tables",
        "writable": True,
        "selectorKinds": {"sheet", "table"},
        "keyFields": ("sheet", "name"),
    },
    "names": {
        "queryKey": "names",
        "artifactPath": ("structure", "namesPath"),
        "artifactKey": "names",
        "writable": True,
        "selectorKinds": {"name", "name-prefix"},
        "keyFields": ("name",),
    },
    "cf": {
        "queryKey": "cf",
        "artifactPath": ("structure", "conditionalFormattingPath"),
        "artifactKey": "rules",
        "writable": True,
        "selectorKinds": {"sheet"},
        "keyFields": ("sheet", "id"),
    },
    "formulas": {
        "queryKey": "formulas",
        "artifactPath": ("structure", "formulasPath"),
        "artifactKey": "formulas",
        "writable": True,
        "selectorKinds": {"sheet"},
        "keyFields": ("sheet", "address"),
    },
    "data-validation": {
        "queryKey": "dataValidation",
        "artifactPath": ("structure", "dataValidationPath"),
        "artifactKey": "rules",
        "writable": True,
        "selectorKinds": {"sheet"},
        "keyFields": ("sheet", "id"),
    },
    "protection": {
        "queryKey": "protection",
        "artifactPath": ("structure", "protectionPath"),
        "artifactKey": None,
        "writable": True,
        "selectorKinds": {"sheet"},
        "keyFields": (),
    },
    "charts": {
        "queryKey": "charts",
        "artifactPath": ("structure", "chartsPath"),
        "artifactKey": "charts",
        "writable": True,
        "selectorKinds": {"sheet"},
        "keyFields": ("sheet", "name"),
        "unsupportedReason": "Package-backed chart sync updates title and series references on existing charts; route creation, deletion, and rich formatting to desktop Excel.",
    },
    "pivots": {
        "queryKey": "pivots",
        "artifactPath": ("structure", "pivotsPath"),
        "artifactKey": "pivots",
        "writable": False,
        "selectorKinds": {"sheet"},
        "keyFields": ("sheet", "name"),
        "unsupportedReason": "Package backend does not yet write pivot metadata.",
    },
    "dimensions": {
        "queryKey": "dimensions",
        "artifactPath": ("structure", "dimensionsPath"),
        "artifactKey": None,
        "writable": True,
        "selectorKinds": {"sheet"},
        "keyFields": (),
    },
    "hyperlinks": {
        "queryKey": "hyperlinks",
        "artifactPath": ("structure", "hyperlinksPath"),
        "artifactKey": "hyperlinks",
        "writable": True,
        "selectorKinds": {"sheet"},
        "keyFields": ("sheet", "address", "target", "location"),
    },
    "comments": {
        "queryKey": "comments",
        "artifactPath": ("structure", "commentsPath"),
        "artifactKey": "comments",
        "writable": True,
        "selectorKinds": {"sheet"},
        "keyFields": ("sheet", "address"),
    },
    "print": {
        "queryKey": "print",
        "artifactPath": ("structure", "printPath"),
        "artifactKey": None,
        "writable": True,
        "selectorKinds": {"sheet"},
        "keyFields": (),
    },
    "styles": {
        "queryKey": "styles",
        "artifactPath": ("structure", "stylesPath"),
        "artifactKey": None,
        "writable": True,
        "selectorKinds": set(),
        "keyFields": (),
    },
    "themes": {
        "queryKey": "themes",
        "artifactPath": ("structure", "themesPath"),
        "artifactKey": None,
        "writable": True,
        "selectorKinds": set(),
        "keyFields": (),
    },
    "pq": {
        "queryKey": "pq",
        "artifactPath": ("powerQuery", "queriesPath"),
        "artifactKey": "queries",
        "writable": False,
        "selectorKinds": {"query"},
        "keyFields": ("name",),
        "unsupportedReason": "Package-backed Power Query edits are not enabled.",
    },
    "connections": {
        "queryKey": "connections",
        "artifactPath": ("powerQuery", "connectionsPath"),
        "artifactKey": "connections",
        "writable": False,
        "selectorKinds": {"query"},
        "keyFields": ("name",),
        "unsupportedReason": "Package-backed connection edits are not enabled.",
    },
    "model": {
        "queryKey": "model",
        "artifactPath": ("powerQuery", "modelPath"),
        "artifactKey": None,
        "writable": False,
        "selectorKinds": set(),
        "keyFields": (),
        "unsupportedReason": "Package-backed model edits are not enabled.",
    },
}


def _safe_workbook_id(workbook_path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", workbook_path.stem).strip(".-") or "workbook"


def _normalize_surface_set(surface_text: str | None, manifest: dict[str, Any] | None = None) -> list[str]:
    surfaces = normalize_surfaces(surface_text)
    if "all-supported" in surfaces or "all" in surfaces:
        manifest_surfaces = set(PACKAGE_SURFACE_SPECS)
        if manifest is not None:
            structure = manifest.get("structure") or {}
            if "workbookPath" not in structure:
                manifest_surfaces.discard("workbook")
            if "sheetsPath" not in structure:
                manifest_surfaces.discard("sheets")
            if "tablesPath" not in structure:
                manifest_surfaces.discard("tables")
            if "namesPath" not in structure:
                manifest_surfaces.discard("names")
            if "conditionalFormattingPath" not in structure:
                manifest_surfaces.discard("cf")
            if "formulasPath" not in structure:
                manifest_surfaces.discard("formulas")
            if "dataValidationPath" not in structure:
                manifest_surfaces.discard("data-validation")
            if "protectionPath" not in structure:
                manifest_surfaces.discard("protection")
            if "chartsPath" not in structure:
                manifest_surfaces.discard("charts")
            if "pivotsPath" not in structure:
                manifest_surfaces.discard("pivots")
            if "dimensionsPath" not in structure:
                manifest_surfaces.discard("dimensions")
            if "hyperlinksPath" not in structure:
                manifest_surfaces.discard("hyperlinks")
            if "commentsPath" not in structure:
                manifest_surfaces.discard("comments")
            if "printPath" not in structure:
                manifest_surfaces.discard("print")
            if "stylesPath" not in structure:
                manifest_surfaces.discard("styles")
            if "themesPath" not in structure:
                manifest_surfaces.discard("themes")
            power_query = manifest.get("powerQuery") or {}
            if "queriesPath" not in power_query:
                manifest_surfaces.discard("pq")
            if "connectionsPath" not in power_query:
                manifest_surfaces.discard("connections")
            if "modelPath" not in power_query:
                manifest_surfaces.discard("model")
        return sorted(manifest_surfaces)
    return surfaces


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_manifest_section(base_dir: Path, section: dict[str, Any] | None, property_name: str) -> Path | None:
    if not section or property_name not in section or not section[property_name]:
        return None
    return (base_dir / Path(section[property_name])).resolve()


def load_sync_manifest(manifest_path: Path, workbook_override: Path | None = None) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest = _load_json(manifest_path)
    root = manifest_path.parent
    if workbook_override:
        workbook_path = workbook_override.resolve()
    else:
        raw_workbook_path = Path(manifest["workbookPath"])
        if raw_workbook_path.is_absolute():
            workbook_path = raw_workbook_path.resolve()
        else:
            candidate = (root / raw_workbook_path).resolve()
            workbook_path = candidate if candidate.exists() else (root.parent / raw_workbook_path).resolve()
    return {
        "version": manifest.get("version", 1),
        "manifestPath": manifest_path,
        "manifestRoot": root,
        "manifest": manifest,
        "workbookPath": workbook_path,
        "workbookId": _safe_workbook_id(workbook_path),
        "structure": manifest.get("structure") or {},
        "powerQuery": manifest.get("powerQuery") or {},
    }


def _serialize_manifest_artifact_paths(manifest_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    structure = manifest.get("structure") or {}
    power_query = manifest.get("powerQuery") or {}
    resolved: dict[str, Any] = {
        "workbookPath": str((manifest_root / Path(manifest["workbookPath"])).resolve()) if not Path(manifest["workbookPath"]).is_absolute() else str(Path(manifest["workbookPath"]).resolve()),
        "structure": {},
        "powerQuery": {},
    }
    for key, value in structure.items():
        if isinstance(value, str):
            resolved["structure"][key] = str((manifest_root / Path(value)).resolve())
    for key, value in power_query.items():
        if isinstance(value, str):
            resolved["powerQuery"][key] = str((manifest_root / Path(value)).resolve())
    return resolved


def validate_manifest_file(manifest_path: Path, *, check_files: bool) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest = _load_json(manifest_path)
    issues: list[str] = []
    warnings: list[str] = []
    if not isinstance(manifest.get("workbookPath"), str) or not manifest.get("workbookPath"):
        issues.append("manifest.workbookPath must be a non-empty string")
    structure = manifest.get("structure")
    if structure is None:
        issues.append("manifest.structure is required")
        structure = {}
    elif not isinstance(structure, dict):
        issues.append("manifest.structure must be an object")
        structure = {}
    power_query = manifest.get("powerQuery") or {}
    if power_query and not isinstance(power_query, dict):
        issues.append("manifest.powerQuery must be an object when present")
        power_query = {}
    version = manifest.get("version", 1)
    if version < 2:
        warnings.append("manifest.version is older than the current bundle contract; migrate to version 2")
    for recommended_key in ("workbookPath", "sheetsPath", "tablesPath", "namesPath", "formulasPath", "dataValidationPath", "protectionPath", "dimensionsPath", "hyperlinksPath", "commentsPath", "printPath", "stylesPath", "themesPath"):
        if recommended_key not in structure:
            warnings.append(f"structure.{recommended_key} is not present")
    duplicate_paths: dict[str, list[str]] = {}
    for section_name, section in (("structure", structure), ("powerQuery", power_query)):
        for key, value in section.items():
            if not isinstance(value, str):
                continue
            duplicate_paths.setdefault(value, []).append(f"{section_name}.{key}")
    for path_value, owners in duplicate_paths.items():
        if len(owners) > 1:
            warnings.append(f"multiple manifest properties target the same artifact path '{path_value}': {', '.join(sorted(owners))}")
    resolved_paths = _serialize_manifest_artifact_paths(manifest_path.parent, manifest) if not issues else {}
    if check_files and resolved_paths:
        workbook_path = Path(resolved_paths["workbookPath"])
        if not workbook_path.exists():
            issues.append(f"resolved workbook path does not exist: {workbook_path}")
        for section_name in ("structure", "powerQuery"):
            for key, resolved in resolved_paths[section_name].items():
                if not Path(resolved).exists():
                    warnings.append(f"{section_name}.{key} does not exist on disk: {resolved}")
    return {
        "manifestPath": str(manifest_path),
        "valid": not issues,
        "issues": issues,
        "warnings": warnings,
        "version": version,
        "resolved": resolved_paths,
    }


def migrate_manifest_payload(manifest_path: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest = _load_json(manifest_path)
    migrated = copy.deepcopy(manifest)
    migrated["version"] = max(2, int(migrated.get("version", 1) or 1))
    structure = migrated.setdefault("structure", {})
    defaults = {
        "workbookPath": "workbook_structure/workbook.json",
        "dimensionsPath": "workbook_structure/dimensions.json",
        "hyperlinksPath": "workbook_structure/hyperlinks.json",
        "commentsPath": "workbook_structure/comments.json",
        "printPath": "workbook_structure/print.json",
        "stylesPath": "workbook_structure/styles.json",
        "themesPath": "workbook_structure/themes.json",
    }
    for key, value in defaults.items():
        if key not in structure:
            structure[key] = value
    return migrated


def create_blank_workbook(workbook_path: Path, spec: dict[str, Any]) -> dict[str, Any]:
    workbook_path = workbook_path.resolve()
    workbook_path.parent.mkdir(parents=True, exist_ok=True)
    sheets = spec.get("sheets") or ["Sheet1"]
    normalized_sheets: list[str] = []
    seen: set[str] = set()
    for raw_name in sheets:
        name = str(raw_name).strip() or f"Sheet{len(normalized_sheets) + 1}"
        if len(name) > 31:
            name = name[:31]
        if name in seen:
            raise ValueError(f"duplicate worksheet name in create spec: {name}")
        seen.add(name)
        normalized_sheets.append(name)

    content_types = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '  <Default Extension="xml" ContentType="application/xml"/>',
        '  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>',
        '  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>',
    ]
    workbook_rels = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
    ]
    workbook_xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">',
        '  <sheets>',
    ]
    for index, sheet_name in enumerate(normalized_sheets, start=1):
        content_types.append(
            f'  <Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
        workbook_rels.append(
            f'  <Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        )
        workbook_xml.append(f'    <sheet name="{sheet_name}" sheetId="{index}" r:id="rId{index}"/>')
    workbook_xml.extend(["  </sheets>", "</workbook>"])
    workbook_rels.append("</Relationships>")
    content_types.append("</Types>")

    title = spec.get("title") or workbook_path.stem
    subject = spec.get("subject") or ""
    description = spec.get("description") or ""
    custom_properties = spec.get("customProperties") or {}

    core_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{title}</dc:title>
  <dc:subject>{subject}</dc:subject>
  <dc:description>{description}</dc:description>
</cp:coreProperties>"""
    app_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Excel Foundry</Application>
  <TitlesOfParts><vt:vector size="{len(normalized_sheets)}" baseType="lpstr">{''.join(f'<vt:lpstr>{name}</vt:lpstr>' for name in normalized_sheets)}</vt:vector></TitlesOfParts>
</Properties>"""
    custom_xml = None
    if custom_properties:
        content_types.insert(-1, '  <Override PartName="/docProps/custom.xml" ContentType="application/vnd.openxmlformats-officedocument.custom-properties+xml"/>')
        props = []
        for index, (key, value) in enumerate(sorted(custom_properties.items()), start=2):
            props.append(
                f'<property fmtid="{{D5CDD505-2E9C-101B-9397-08002B2CF9AE}}" pid="{index}" name="{key}"><vt:lpwstr xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">{value}</vt:lpwstr></property>'
            )
        custom_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties" '
            'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
            + "".join(props)
            + "</Properties>"
        )

    with zipfile.ZipFile(workbook_path, "w", compression=zipfile.ZIP_DEFLATED) as workbook_zip:
        workbook_zip.writestr("[Content_Types].xml", "\n".join(content_types))
        workbook_zip.writestr("_rels/.rels", """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
  """ + ('<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties" Target="docProps/custom.xml"/>' if custom_xml is not None else '') + """
</Relationships>""")
        workbook_zip.writestr("xl/workbook.xml", "\n".join(workbook_xml))
        workbook_zip.writestr("xl/_rels/workbook.xml.rels", "\n".join(workbook_rels))
        for index in range(1, len(normalized_sheets) + 1):
            workbook_zip.writestr(
                f"xl/worksheets/sheet{index}.xml",
                '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData /></worksheet>',
            )
        workbook_zip.writestr("docProps/core.xml", core_xml)
        workbook_zip.writestr("docProps/app.xml", app_xml)
        if custom_xml is not None:
            workbook_zip.writestr("docProps/custom.xml", custom_xml)
    return build_inspection_payload(build_query_payload(workbook_path, ["workbook", "sheets"]))


def compare_workbook_payloads(left_workbook: Path, right_workbook: Path, surfaces: list[str]) -> dict[str, Any]:
    normalized_surfaces = surfaces or ["workbook", "sheets", "tables", "names", "formulas", "data-validation", "protection", "cf", "pivots", "hyperlinks", "comments", "print", "dimensions", "styles", "themes", "pq", "connections", "model"]
    left_payload = build_query_payload(left_workbook, normalized_surfaces)
    right_payload = build_query_payload(right_workbook, normalized_surfaces)
    surface_results: list[dict[str, Any]] = []
    overall_match = True
    for surface in normalized_surfaces:
        query_key = PACKAGE_SURFACE_SPECS.get(surface, {}).get("queryKey", surface)
        summary = _summarize_diff(surface, left_payload.get(query_key), right_payload.get(query_key))
        overall_match = overall_match and summary["match"]
        surface_results.append({"surface": surface, "match": summary["match"], "summary": summary})
    return {
        "leftWorkbookPath": str(left_workbook.resolve()),
        "rightWorkbookPath": str(right_workbook.resolve()),
        "backend": "package",
        "match": overall_match,
        "surfaces": surface_results,
    }


def _surface_artifact_path(bundle: dict[str, Any], surface: str) -> Path | None:
    spec = PACKAGE_SURFACE_SPECS[surface]
    section_name, property_name = spec["artifactPath"]
    section = bundle[section_name]
    return _resolve_manifest_section(bundle["manifestRoot"], section, property_name)


def _normalize_artifact_payload(surface: str, payload: Any) -> Any:
    spec = PACKAGE_SURFACE_SPECS[surface]
    key = spec["artifactKey"]
    if key is None:
        return payload
    return payload.get(key, [])


def _wrap_artifact_payload(surface: str, payload: Any) -> Any:
    spec = PACKAGE_SURFACE_SPECS[surface]
    key = spec["artifactKey"]
    if key is None:
        return payload
    return {key: payload}


def load_repo_surface_payload(bundle: dict[str, Any], surface: str) -> Any:
    artifact_path = _surface_artifact_path(bundle, surface)
    if artifact_path is None or not artifact_path.exists():
        return None
    return _normalize_artifact_payload(surface, _load_json(artifact_path))


def _selected_surface_items(surface: str, payload: Any, selectors: dict[str, set[str]]) -> Any:
    if payload is None:
        return None
    if surface == "sheets":
        selected_sheets = selectors["sheet"]
        if not selected_sheets:
            return payload
        return [item for item in payload if item.get("name") in selected_sheets]
    if surface == "names":
        selected_names = selectors["name"]
        prefixes = selectors["name-prefix"]
        if not selected_names and not prefixes:
            return payload
        return [
            item
            for item in payload
            if item.get("name") in selected_names
            or any(item.get("name", "").startswith(prefix) for prefix in prefixes)
        ]
    if surface in {"tables", "cf", "formulas", "data-validation", "charts", "pivots", "hyperlinks", "comments"}:
        selected_sheets = selectors["sheet"]
        if surface == "tables":
            selected_tables = selectors["table"]
            if not selected_sheets and not selected_tables:
                return payload
            return [
                item
                for item in payload
                if (not selected_sheets or item.get("sheet") in selected_sheets)
                and (not selected_tables or item.get("name") in selected_tables)
            ]
        if not selected_sheets:
            return payload
        return [item for item in payload if item.get("sheet") in selected_sheets]
    if surface in {"dimensions", "print"}:
        selected_sheets = selectors["sheet"]
        if not selected_sheets:
            return payload
        return {"sheets": [item for item in payload.get("sheets", []) if item.get("sheet") in selected_sheets]}
    if surface == "protection":
        selected_sheets = selectors["sheet"]
        if not selected_sheets:
            return payload
        return {
            "workbook": payload.get("workbook"),
            "worksheets": [item for item in payload.get("worksheets", []) if item.get("sheet") in selected_sheets],
        }
    if surface in {"pq", "connections"}:
        selected_queries = selectors["query"]
        if not selected_queries:
            return payload
        return [item for item in payload if item.get("name") in selected_queries or item.get("connectionName") in selected_queries]
    return payload


def _item_key(surface: str, item: dict[str, Any]) -> str:
    fields = PACKAGE_SURFACE_SPECS[surface]["keyFields"]
    return "|".join(str(item.get(field, "")) for field in fields)


def _index_surface(surface: str, payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if surface in {"workbook", "dimensions", "print", "styles", "themes", "model"}:
        return {"__value__": payload}
    if surface == "protection":
        return {
            "__workbook__": payload.get("workbook"),
            **{f"sheet|{item.get('sheet', '')}": item for item in payload.get("worksheets", [])},
        }
    return {_item_key(surface, item): item for item in payload}


def _from_index(surface: str, payload_index: dict[str, Any]) -> Any:
    if surface in {"workbook", "dimensions", "print", "styles", "themes", "model"}:
        return payload_index.get("__value__")
    if surface == "protection":
        worksheets = [value for key, value in payload_index.items() if key.startswith("sheet|") and value is not None]
        return {
            "workbook": payload_index.get("__workbook__"),
            "worksheets": sorted(worksheets, key=lambda item: item.get("sheet", "")),
        }
    return sorted(
        [value for value in payload_index.values() if value is not None],
        key=lambda item: tuple(str(item.get(field, "")) for field in PACKAGE_SURFACE_SPECS[surface]["keyFields"]),
    )


def _summarize_diff(surface: str, repo_payload: Any, workbook_payload: Any) -> dict[str, Any]:
    repo_index = _index_surface(surface, repo_payload)
    workbook_index = _index_surface(surface, workbook_payload)
    changed: list[str] = []
    repo_only: list[str] = []
    workbook_only: list[str] = []
    for key in sorted(set(repo_index) | set(workbook_index)):
        repo_item = repo_index.get(key)
        workbook_item = workbook_index.get(key)
        if key not in repo_index:
            workbook_only.append(key)
        elif key not in workbook_index:
            repo_only.append(key)
        elif repo_item != workbook_item:
            changed.append(key)
    return {
        "match": not changed and not repo_only and not workbook_only,
        "counts": {
            "changed": len(changed),
            "repoOnly": len(repo_only),
            "workbookOnly": len(workbook_only),
        },
        "whyUnequal": {
            "changed": changed,
            "repoOnly": repo_only,
            "workbookOnly": workbook_only,
        },
    }


def _state_surface_path(state_root: Path, bundle: dict[str, Any], surface: str) -> Path:
    return state_root / bundle["workbookId"] / surface / "baseline.json"


def _load_baseline(state_root: Path, bundle: dict[str, Any], surface: str) -> Any:
    path = _state_surface_path(state_root, bundle, surface)
    if not path.exists():
        return None
    payload = _load_json(path)
    return payload.get("data")


def _write_baseline(state_root: Path, bundle: dict[str, Any], surface: str, payload: Any) -> None:
    path = _state_surface_path(state_root, bundle, surface)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(
        path,
        {
            "workbookPath": str(bundle["workbookPath"]),
            "surface": surface,
            "data": payload,
        },
    )


def _merge_surface(surface: str, baseline: Any, repo_payload: Any, workbook_payload: Any) -> tuple[Any, list[str], dict[str, int]]:
    baseline_index = _index_surface(surface, baseline)
    repo_index = _index_surface(surface, repo_payload)
    workbook_index = _index_surface(surface, workbook_payload)
    merged: dict[str, Any] = {}
    conflicts: list[str] = []
    counts = {"mergedRepo": 0, "preservedWorkbook": 0, "unchanged": 0}
    for key in sorted(set(baseline_index) | set(repo_index) | set(workbook_index)):
        base_item = baseline_index.get(key)
        repo_item = repo_index.get(key)
        workbook_item = workbook_index.get(key)
        repo_changed = repo_item != base_item
        workbook_changed = workbook_item != base_item
        if repo_changed and workbook_changed and repo_item != workbook_item:
            conflicts.append(key)
            if workbook_item is not None:
                merged[key] = workbook_item
            continue
        if repo_changed:
            counts["mergedRepo"] += 1
            if repo_item is not None:
                merged[key] = repo_item
            continue
        if workbook_changed:
            counts["preservedWorkbook"] += 1
            if workbook_item is not None:
                merged[key] = workbook_item
            continue
        counts["unchanged"] += 1
        if workbook_item is not None:
            merged[key] = workbook_item
        elif repo_item is not None:
            merged[key] = repo_item
        elif base_item is not None:
            merged[key] = base_item
    return _from_index(surface, merged), conflicts, counts


def _sheet_xml_path(package: WorkbookPackage, sheet_name: str) -> str:
    for sheet in package.sheets:
        if sheet["name"] == sheet_name:
            return sheet["path"]
    raise ValueError(f"Unknown worksheet: {sheet_name}")


def _get_or_create_row(sheet_data: ET.Element, row_number: int) -> ET.Element:
    for row in sheet_data.findall("main:row", NS):
        if int(row.attrib.get("r", "0") or "0") == row_number:
            return row
    row = ET.SubElement(sheet_data, f"{{{NS['main']}}}row", {"r": str(row_number)})
    rows = sorted(sheet_data.findall("main:row", NS), key=lambda item: int(item.attrib.get("r", "0") or "0"))
    for item in list(sheet_data):
        sheet_data.remove(item)
    for item in rows:
        sheet_data.append(item)
    return row


def _get_or_create_cell(row: ET.Element, cell_ref: str) -> ET.Element:
    for cell in row.findall("main:c", NS):
        if cell.attrib.get("r") == cell_ref:
            return cell
    cell = ET.SubElement(row, f"{{{NS['main']}}}c", {"r": cell_ref})
    cells = sorted(row.findall("main:c", NS), key=lambda item: _cell_ref_to_row_col(item.attrib.get("r", "A1")))
    for item in list(row):
        row.remove(item)
    for item in cells:
        row.append(item)
    return cell


def _set_text_child(parent: ET.Element, child_name: str, value: str | None) -> None:
    child = parent.find(f"main:{child_name}", NS)
    if value is None:
        if child is not None:
            parent.remove(child)
        return
    if child is None:
        child = ET.SubElement(parent, f"{{{NS['main']}}}{child_name}")
    child.text = value


def _replace_simple_properties(prop_root: ET.Element, properties: dict[str, Any]) -> None:
    existing_tags = {(_local_name(child.tag), child.tag) for child in list(prop_root)}
    for child in list(prop_root):
        prop_root.remove(child)
    for key, value in properties.items():
        resolved_tag = next((full_tag for local_name, full_tag in existing_tags if local_name == key), key)
        child = ET.SubElement(prop_root, resolved_tag)
        child.text = str(value)


def _normalize_scalar_for_cell(value: Any) -> tuple[str | None, str]:
    if value is None:
        return None, ""
    if isinstance(value, bool):
        return "b", "1" if value else "0"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return None, str(value)
    return "str", str(value)


def _apply_cell_value_to_sheet(root: ET.Element, cell_ref: str, value: Any) -> None:
    sheet_data = root.find("main:sheetData", NS)
    if sheet_data is None:
        sheet_data = ET.SubElement(root, f"{{{NS['main']}}}sheetData")
    row_number, _ = _cell_ref_to_row_col(cell_ref)
    row = _get_or_create_row(sheet_data, row_number)
    cell = _get_or_create_cell(row, cell_ref)
    formula_node = cell.find("main:f", NS)
    if formula_node is not None:
        cell.remove(formula_node)
    value_node = cell.find("main:v", NS)
    if value_node is None:
        value_node = ET.SubElement(cell, f"{{{NS['main']}}}v")
    cell_type, scalar = _normalize_scalar_for_cell(value)
    if cell_type:
        cell.attrib["t"] = cell_type
    elif "t" in cell.attrib:
        del cell.attrib["t"]
    value_node.text = scalar


def apply_direct_sheet_create(workbook_path: Path, sheet_name: str) -> dict[str, Any]:
    package = WorkbookPackage(workbook_path)
    try:
        if any(sheet["name"] == sheet_name for sheet in package.sheets):
            raise ValueError(f"Worksheet already exists: {sheet_name}")
        sheet_ids = [int(sheet["sheetId"]) for sheet in package.sheets if str(sheet.get("sheetId", "")).isdigit()]
        next_sheet_id = (max(sheet_ids) + 1) if sheet_ids else 1
        rel_ids = []
        for rel_id in package.workbook_rels:
            match = re.match(r"rId(\d+)$", rel_id)
            if match:
                rel_ids.append(int(match.group(1)))
        next_rel_id = f"rId{(max(rel_ids) + 1) if rel_ids else 1}"
        sheet_index = len(package.sheets) + 1
        worksheet_path = f"xl/worksheets/sheet{sheet_index}.xml"

        workbook_root = package.workbook_xml
        sheets_node = workbook_root.find("main:sheets", NS)
        if sheets_node is None:
            sheets_node = ET.SubElement(workbook_root, f"{{{NS['main']}}}sheets")
        ET.SubElement(
            sheets_node,
            f"{{{NS['main']}}}sheet",
            {
                "name": sheet_name,
                "sheetId": str(next_sheet_id),
                f"{{{NS['rel']}}}id": next_rel_id,
            },
        )

        workbook_rels_root = package._read_xml("xl/_rels/workbook.xml.rels")
        ET.SubElement(
            workbook_rels_root,
            f"{{{NS['pkgrel']}}}Relationship",
            {
                "Id": next_rel_id,
                "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet",
                "Target": f"worksheets/{PurePosixPath(worksheet_path).name}",
            },
        )

        content_types_root = package._read_xml("[Content_Types].xml")
        ET.SubElement(
            content_types_root,
            "{http://schemas.openxmlformats.org/package/2006/content-types}Override",
            {
                "PartName": f"/{worksheet_path}",
                "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml",
            },
        )

        worksheet_root = ET.fromstring(
            b'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData /></worksheet>'
        )
        updates = {
            "xl/workbook.xml": ET.tostring(workbook_root, encoding="utf-8", xml_declaration=True),
            "xl/_rels/workbook.xml.rels": ET.tostring(workbook_rels_root, encoding="utf-8", xml_declaration=True),
            "[Content_Types].xml": ET.tostring(content_types_root, encoding="utf-8", xml_declaration=True),
            worksheet_path: ET.tostring(worksheet_root, encoding="utf-8", xml_declaration=True),
        }
    finally:
        package.close()
    _rewrite_workbook_package(workbook_path, updates)
    return {"status": "applied", "sheet": sheet_name, "created": True}


def apply_direct_sheet_delete(workbook_path: Path, sheet_name: str, destructive: bool) -> dict[str, Any]:
    if not destructive:
        return {
            "status": "blocked",
            "sheet": sheet_name,
            "destructiveRequired": True,
            "message": "sheet delete requires --destructive so agents cannot remove workbook structure by accident.",
        }
    package = WorkbookPackage(workbook_path)
    try:
        if len(package.sheets) <= 1:
            raise ValueError("Cannot delete the last worksheet in a workbook.")
        workbook_root = package.workbook_xml
        sheets_node = workbook_root.find("main:sheets", NS)
        if sheets_node is None:
            raise ValueError("Workbook does not contain a sheets collection.")
        sheet_nodes = list(sheets_node.findall("main:sheet", NS))
        target_index = next((index for index, item in enumerate(package.sheets) if item["name"] == sheet_name), None)
        if target_index is None:
            raise ValueError(f"Unknown worksheet: {sheet_name}")
        sheet_node = sheet_nodes[target_index]
        rel_id = sheet_node.attrib.get(f"{{{NS['rel']}}}id")
        sheet_path = package.sheets[target_index]["path"]
        sheet_rels_path = _sheet_rels_path(sheet_path)
        sheets_node.remove(sheet_node)

        defined_names = workbook_root.find("main:definedNames", NS)
        if defined_names is not None:
            for item in list(defined_names):
                local_sheet_id = item.attrib.get("localSheetId")
                if local_sheet_id is None or not local_sheet_id.isdigit():
                    continue
                local_index = int(local_sheet_id)
                if local_index == target_index:
                    defined_names.remove(item)
                elif local_index > target_index:
                    item.attrib["localSheetId"] = str(local_index - 1)

        workbook_rels_root = package._read_xml("xl/_rels/workbook.xml.rels")
        if rel_id:
            for rel in list(workbook_rels_root.findall("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship")):
                if rel.attrib.get("Id") == rel_id:
                    workbook_rels_root.remove(rel)

        content_types_root = package._read_xml("[Content_Types].xml")
        for override in list(content_types_root.findall("{http://schemas.openxmlformats.org/package/2006/content-types}Override")):
            if override.attrib.get("PartName") == f"/{sheet_path}":
                content_types_root.remove(override)

        deletes = {sheet_path, sheet_rels_path}
        for relationship in package.sheets[target_index].get("rels", {}).values():
            target = relationship.get("target")
            if target and target.startswith("xl/"):
                deletes.add(target)

        updates = {
            "xl/workbook.xml": ET.tostring(workbook_root, encoding="utf-8", xml_declaration=True),
            "xl/_rels/workbook.xml.rels": ET.tostring(workbook_rels_root, encoding="utf-8", xml_declaration=True),
            "[Content_Types].xml": ET.tostring(content_types_root, encoding="utf-8", xml_declaration=True),
        }
    finally:
        package.close()
    _rewrite_workbook_package(workbook_path, updates, deletes=deletes)
    return {
        "status": "applied",
        "sheet": sheet_name,
        "deleted": True,
        "deletedParts": sorted(deletes),
    }


def apply_direct_sheet_visibility(workbook_path: Path, sheet_name: str, visibility: str) -> dict[str, Any]:
    package = WorkbookPackage(workbook_path)
    try:
        workbook_root = package.workbook_xml
        sheet_node = next(
            (item for item in workbook_root.findall("main:sheets/main:sheet", NS) if item.attrib.get("name") == sheet_name),
            None,
        )
        if sheet_node is None:
            raise ValueError(f"Unknown worksheet: {sheet_name}")
        if visibility == "visible":
            sheet_node.attrib.pop("state", None)
        else:
            sheet_node.attrib["state"] = visibility
        updates = {"xl/workbook.xml": ET.tostring(workbook_root, encoding="utf-8", xml_declaration=True)}
    finally:
        package.close()
    _rewrite_workbook_package(workbook_path, updates)
    return {"status": "applied", "sheet": sheet_name, "visibility": visibility}


def apply_direct_sheet_reorder(workbook_path: Path, sheet_names: list[str]) -> dict[str, Any]:
    if not sheet_names:
        raise ValueError("sheet reorder requires one or more --sheet values in the desired front-to-back order.")
    package = WorkbookPackage(workbook_path)
    try:
        workbook_root = package.workbook_xml
        sheets_node = workbook_root.find("main:sheets", NS)
        if sheets_node is None:
            raise ValueError("Workbook does not contain a sheets collection.")
        sheet_nodes = list(sheets_node.findall("main:sheet", NS))
        by_name = {item.attrib.get("name", ""): item for item in sheet_nodes}
        missing = [name for name in sheet_names if name not in by_name]
        if missing:
            raise ValueError(f"Unknown worksheet(s): {', '.join(missing)}")
        for item in sheet_nodes:
            sheets_node.remove(item)
        ordered_names = []
        for name in sheet_names:
            if name not in ordered_names:
                ordered_names.append(name)
        ordered_names.extend(item.attrib.get("name", "") for item in sheet_nodes if item.attrib.get("name", "") not in ordered_names)
        for name in ordered_names:
            sheets_node.append(by_name[name])
        updates = {"xl/workbook.xml": ET.tostring(workbook_root, encoding="utf-8", xml_declaration=True)}
    finally:
        package.close()
    _rewrite_workbook_package(workbook_path, updates)
    return {"status": "applied", "order": ordered_names}


def apply_direct_names(workbook_path: Path, names: list[dict[str, Any]]) -> dict[str, Any]:
    package = WorkbookPackage(workbook_path)
    try:
        root = package.workbook_xml
        defined_names = root.find("main:definedNames", NS)
        if defined_names is None:
            defined_names = ET.Element(f"{{{NS['main']}}}definedNames")
            sheets = root.find("main:sheets", NS)
            insert_at = list(root).index(sheets) + 1 if sheets is not None else len(list(root))
            root.insert(insert_at, defined_names)
        existing = {item.attrib.get("name", ""): item for item in list(defined_names)}
        applied = []
        for item in names:
            name = item["name"]
            node = existing.get(name)
            if item.get("delete"):
                if node is not None:
                    defined_names.remove(node)
                    applied.append({"name": name, "deleted": True})
                continue
            if node is None:
                node = ET.SubElement(defined_names, f"{{{NS['main']}}}definedName", {"name": name})
            node.text = item.get("refersTo", "")
            if item.get("hidden") is not None:
                node.attrib["hidden"] = "1" if item.get("hidden") else "0"
            applied.append({"name": name, "refersTo": node.text, "deleted": False})
        updates = {"xl/workbook.xml": ET.tostring(root, encoding="utf-8", xml_declaration=True)}
    finally:
        package.close()
    _rewrite_workbook_package(workbook_path, updates)
    return {"status": "applied", "names": applied}


def apply_direct_cells(workbook_path: Path, sheet_name: str, assignments: list[dict[str, Any]]) -> dict[str, Any]:
    package = WorkbookPackage(workbook_path)
    try:
        sheet_path = _sheet_xml_path(package, sheet_name)
        root = package._read_xml(sheet_path)
        for assignment in assignments:
            _apply_cell_value_to_sheet(root, assignment["address"].replace("$", "").upper(), assignment.get("value"))
        updates = {sheet_path: ET.tostring(root, encoding="utf-8", xml_declaration=True)}
    finally:
        package.close()
    _rewrite_workbook_package(workbook_path, updates)
    return {"status": "applied", "sheet": sheet_name, "cells": assignments}


def _serialize_xml(element: ET.Element) -> bytes:
    return ET.tostring(element, encoding="utf-8", xml_declaration=True)


def _relationships_root() -> ET.Element:
    return ET.Element("{http://schemas.openxmlformats.org/package/2006/relationships}Relationships")


def _sheet_rels_path(sheet_path: str) -> str:
    sheet_name = PurePosixPath(sheet_path).name
    return f"xl/worksheets/_rels/{sheet_name}.rels"


def _comments_part_path(sheet_path: str) -> str:
    stem = PurePosixPath(sheet_path).stem
    digits = "".join(ch for ch in stem if ch.isdigit()) or "1"
    return f"xl/comments{digits}.xml"


def _ensure_override(content_types_root: ET.Element, part_name: str, content_type: str) -> None:
    for item in content_types_root.findall("{http://schemas.openxmlformats.org/package/2006/content-types}Override"):
        if item.attrib.get("PartName") == part_name:
            item.attrib["ContentType"] = content_type
            return
    ET.SubElement(
        content_types_root,
        "{http://schemas.openxmlformats.org/package/2006/content-types}Override",
        {"PartName": part_name, "ContentType": content_type},
    )


def _next_relationship_id(rels_root: ET.Element) -> str:
    existing = {
        int(item.attrib["Id"][3:])
        for item in rels_root.findall("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship")
        if item.attrib.get("Id", "").startswith("rId") and item.attrib["Id"][3:].isdigit()
    }
    next_value = 1
    while next_value in existing:
        next_value += 1
    return f"rId{next_value}"


def _upsert_relationship(
    rels_root: ET.Element,
    *,
    rel_type: str,
    target: str,
    target_mode: str | None = None,
) -> str:
    for item in rels_root.findall("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"):
        if item.attrib.get("Type") != rel_type:
            continue
        if item.attrib.get("Target") != target:
            continue
        if (item.attrib.get("TargetMode") or None) != target_mode:
            continue
        return item.attrib["Id"]
    rel_id = _next_relationship_id(rels_root)
    attrs = {"Id": rel_id, "Type": rel_type, "Target": target}
    if target_mode:
        attrs["TargetMode"] = target_mode
    ET.SubElement(rels_root, "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship", attrs)
    return rel_id


def _remove_relationships_by_type(rels_root: ET.Element, rel_type: str) -> None:
    for item in list(rels_root.findall("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship")):
        if item.attrib.get("Type") == rel_type:
            rels_root.remove(item)


def _chart_part_entries(package: WorkbookPackage) -> list[dict[str, str | None]]:
    entries: list[dict[str, str | None]] = []
    for sheet in package.sheets:
        if sheet.get("sheetType") == "worksheet":
            for rel in sheet["rels"].values():
                if not rel["type"].endswith("/drawing"):
                    continue
                drawing_path = rel["target"]
                try:
                    drawing_root = package._read_xml(drawing_path)
                except KeyError:
                    continue
                drawing_rels = package._read_relationships(package._drawing_relationships_path(drawing_path))
                for anchor_node in drawing_root.findall("xdr:twoCellAnchor", NS):
                    chart_node = anchor_node.find("xdr:graphicFrame/a:graphic/a:graphicData/c:chart", NS)
                    if chart_node is None:
                        continue
                    chart_rel_id = chart_node.attrib.get(f"{{{NS['rel']}}}id")
                    chart_rel = drawing_rels.get(chart_rel_id or "")
                    if not chart_rel:
                        continue
                    c_nv_pr = anchor_node.find("xdr:graphicFrame/xdr:nvGraphicFramePr/xdr:cNvPr", NS)
                    entries.append(
                        {
                            "sheet": sheet["name"],
                            "name": c_nv_pr.attrib.get("name") if c_nv_pr is not None else None,
                            "path": chart_rel["target"],
                        }
                    )
        elif sheet.get("sheetType") == "chartsheet":
            try:
                root = package._read_xml(sheet["path"])
            except KeyError:
                continue
            drawing_node = root.find("main:drawing", NS)
            if drawing_node is None:
                continue
            drawing_rel_id = drawing_node.attrib.get(f"{{{NS['rel']}}}id")
            drawing_rel = sheet["rels"].get(drawing_rel_id or "")
            if not drawing_rel:
                continue
            drawing_rels = package._read_relationships(package._drawing_relationships_path(drawing_rel["target"]))
            chart_rel = next((rel for rel in drawing_rels.values() if rel["type"].endswith("/chart")), None)
            if chart_rel:
                entries.append({"sheet": sheet["name"], "name": sheet["name"], "path": chart_rel["target"]})
    return entries


def _split_series_arguments(formula: str) -> list[str]:
    text = formula.strip()
    if text.startswith("="):
        text = text[1:].strip()
    if not text.upper().startswith("SERIES(") or not text.endswith(")"):
        return []
    body = text[text.find("(") + 1 : -1]
    args: list[str] = []
    current: list[str] = []
    in_string = False
    brace_depth = 0
    for char in body:
        if char == '"':
            in_string = not in_string
            current.append(char)
            continue
        if not in_string:
            if char == "{":
                brace_depth += 1
            elif char == "}":
                brace_depth = max(0, brace_depth - 1)
            elif char == "," and brace_depth == 0:
                args.append("".join(current).strip())
                current = []
                continue
        current.append(char)
    args.append("".join(current).strip())
    return args


def _series_formula_parts(series_spec: dict[str, Any]) -> dict[str, str | None]:
    parts = {
        "nameFormula": series_spec.get("nameFormula"),
        "categoriesFormula": series_spec.get("categoriesFormula"),
        "valuesFormula": series_spec.get("valuesFormula"),
        "bubbleSizeFormula": series_spec.get("bubbleSizeFormula"),
    }
    if any(value for value in parts.values()):
        return {key: (str(value) if value is not None else None) for key, value in parts.items()}
    args = _split_series_arguments(str(series_spec.get("formula") or ""))
    if not args:
        return parts
    return {
        "nameFormula": args[0] if len(args) > 0 and args[0] else None,
        "categoriesFormula": args[1] if len(args) > 1 and args[1] else None,
        "valuesFormula": args[2] if len(args) > 2 and args[2] else None,
        "bubbleSizeFormula": None,
    }


def _ensure_chart_child(parent: ET.Element, child_name: str) -> ET.Element:
    child = parent.find(f"c:{child_name}", NS)
    if child is None:
        child = ET.SubElement(parent, f"{{{NS['c']}}}{child_name}")
    return child


def _set_chart_ref_formula(parent: ET.Element | None, ref_child_name: str, formula: str | None) -> bool:
    if parent is None or formula is None:
        return False
    ref_node = parent.find(f"c:{ref_child_name}", NS)
    if ref_node is None:
        ref_node = ET.SubElement(parent, f"{{{NS['c']}}}{ref_child_name}")
    formula_node = ref_node.find("c:f", NS)
    if formula_node is None:
        formula_node = ET.SubElement(ref_node, f"{{{NS['c']}}}f")
    changed = formula_node.text != formula
    formula_node.text = formula
    for cache in list(ref_node):
        if _local_name(cache.tag) in {"numCache", "strCache"}:
            ref_node.remove(cache)
            changed = True
    return changed


def _apply_chart_relationship_spec(chart_root: ET.Element, chart_spec: dict[str, Any]) -> bool:
    changed = False
    title = chart_spec.get("title")
    if title is not None:
        title_node = chart_root.find("c:chart/c:title", NS)
        text_nodes = title_node.findall(".//a:t", NS) if title_node is not None else []
        if text_nodes:
            if text_nodes[0].text != str(title):
                changed = True
            text_nodes[0].text = str(title)
            for extra in text_nodes[1:]:
                if extra.text:
                    changed = True
                extra.text = ""

    desired_series = chart_spec.get("series") or []
    if not isinstance(desired_series, list):
        return changed
    existing_series = chart_root.findall(".//c:ser", NS)
    for index, series_spec in enumerate(desired_series):
        if index >= len(existing_series) or not isinstance(series_spec, dict):
            continue
        series_node = existing_series[index]
        parts = _series_formula_parts(series_spec)
        if parts.get("nameFormula"):
            tx_node = _ensure_chart_child(series_node, "tx")
            changed = _set_chart_ref_formula(tx_node, "strRef", parts["nameFormula"]) or changed
        handled_formula_keys: set[str] = set()
        for axis_name, formula_key, ref_child_name in (
            ("cat", "categoriesFormula", "strRef"),
            ("xVal", "categoriesFormula", "numRef"),
            ("val", "valuesFormula", "numRef"),
            ("yVal", "valuesFormula", "numRef"),
            ("bubbleSize", "bubbleSizeFormula", "numRef"),
        ):
            if formula_key in handled_formula_keys:
                continue
            formula = parts.get(formula_key)
            if formula is None:
                continue
            axis_node = series_node.find(f"c:{axis_name}", NS)
            if axis_node is not None:
                changed = _set_chart_ref_formula(axis_node, ref_child_name, formula) or changed
                handled_formula_keys.add(formula_key)
    return changed


def _validated_package_xml_update(part_spec: dict[str, Any], surface: str) -> tuple[str, bytes]:
    raw_path = str(part_spec.get("path") or "")
    part_path = str(PurePosixPath(raw_path))
    if part_path.startswith("/") or ".." in PurePosixPath(part_path).parts:
        raise ValueError(f"{surface} package part path must be relative and stay inside the workbook package: {raw_path}")
    if surface == "styles" and part_path != "xl/styles.xml":
        raise ValueError("styles package sync can only update xl/styles.xml")
    if surface == "themes" and (not part_path.startswith("xl/theme/") or not part_path.endswith(".xml")):
        raise ValueError("themes package sync can only update XML parts below xl/theme/")
    xml_text = part_spec.get("xml")
    if not isinstance(xml_text, str) or not xml_text.strip():
        raise ValueError(f"{surface} package part {part_path} requires a non-empty xml string")
    content = xml_text.encode("utf-8")
    ET.fromstring(content)
    return part_path, content


def apply_package_surface_push(workbook_path: Path, surface: str, payload: Any, selectors: dict[str, set[str]]) -> list[str]:
    package = WorkbookPackage(workbook_path)
    updates: dict[str, bytes] = {}
    messages: list[str] = []
    try:
        if surface == "workbook":
            root = package.workbook_xml
            workbook_spec = payload or {}
            calculation_spec = workbook_spec.get("calculation") or {}
            calc_node = root.find("main:calcPr", NS)
            if calculation_spec:
                if calc_node is None:
                    calc_node = ET.SubElement(root, f"{{{NS['main']}}}calcPr")
                calc_attr_map = {
                    "mode": "calcMode",
                    "calcCompleted": "calcCompleted",
                    "calcOnSave": "calcOnSave",
                    "fullCalcOnLoad": "fullCalcOnLoad",
                    "forceFullCalc": "forceFullCalc",
                    "iterate": "iterate",
                    "iterateCount": "iterateCount",
                    "iterateDelta": "iterateDelta",
                    "refMode": "refMode",
                }
                for key, value in calculation_spec.items():
                    attr_name = calc_attr_map.get(key, key)
                    if value is None:
                        calc_node.attrib.pop(attr_name, None)
                    else:
                        calc_node.attrib[attr_name] = "1" if value is True else "0" if value is False else str(value)
            elif calc_node is not None:
                root.remove(calc_node)
            updates["xl/workbook.xml"] = _serialize_xml(root)

            for prop_name, part_path, root_tag, namespaces in (
                ("core", "docProps/core.xml", "cp:coreProperties", {
                    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
                    "dc": "http://purl.org/dc/elements/1.1/",
                    "dcterms": "http://purl.org/dc/terms/",
                    "dcmitype": "http://purl.org/dc/dcmitype/",
                    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
                }),
                ("app", "docProps/app.xml", "Properties", {
                    "": "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties",
                    "vt": "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes",
                }),
            ):
                properties = ((workbook_spec.get("properties") or {}).get(prop_name)) or {}
                try:
                    prop_root = package._read_xml(part_path)
                except KeyError:
                    continue
                _replace_simple_properties(prop_root, properties)
                updates[part_path] = _serialize_xml(prop_root)

            custom_properties = ((workbook_spec.get("properties") or {}).get("custom")) or {}
            if custom_properties:
                custom_root = ET.Element(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/custom-properties}Properties",
                    {"xmlns:vt": "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"},
                )
                for index, (key, value) in enumerate(custom_properties.items(), start=2):
                    prop = ET.SubElement(
                        custom_root,
                        "{http://schemas.openxmlformats.org/officeDocument/2006/custom-properties}property",
                        {
                            "fmtid": "{D5CDD505-2E9C-101B-9397-08002B2CF9AE}",
                            "pid": str(index),
                            "name": str(key),
                        },
                    )
                    child = ET.SubElement(prop, "{http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes}lpwstr")
                    child.text = str(value)
                updates["docProps/custom.xml"] = _serialize_xml(custom_root)
            messages.append("Applied workbook metadata and calculation settings.")
        elif surface == "sheets":
            existing_names = {sheet["name"] for sheet in package.sheets}
            for item in payload or []:
                sheet_name = str(item.get("name") or "").strip()
                if not sheet_name:
                    continue
                if item.get("delete") or item.get("deleted"):
                    if sheet_name in existing_names:
                        raise ValueError("Sheet deletions require the direct sheet-delete command with --destructive.")
                    continue
                if sheet_name not in existing_names:
                    messages.append(f"Sheet {sheet_name} would be created by direct sheet-create; package sync skips creation inside grouped writes.")
            messages.append("Reviewed sheet structure manifest; destructive deletes are guarded by sheet-delete.")
        elif surface == "names":
            root = package.workbook_xml
            defined_names = root.find("main:definedNames", NS)
            if defined_names is None:
                defined_names = ET.Element(f"{{{NS['main']}}}definedNames")
                sheets = root.find("main:sheets", NS)
                insert_at = list(root).index(sheets) + 1 if sheets is not None else len(list(root))
                root.insert(insert_at, defined_names)
            selected_names = selectors["name"]
            prefixes = selectors["name-prefix"]
            should_target = bool(selected_names or prefixes)
            preserved = []
            for item in list(defined_names):
                name = item.attrib.get("name", "")
                targeted = (name in selected_names) or any(name.startswith(prefix) for prefix in prefixes)
                if should_target and not targeted:
                    preserved.append(item)
                defined_names.remove(item)
            for item in preserved:
                defined_names.append(item)
            for item in payload:
                node = ET.SubElement(defined_names, f"{{{NS['main']}}}definedName", {"name": item["name"]})
                node.text = item.get("refersTo", "")
            updates["xl/workbook.xml"] = _serialize_xml(root)
            messages.append(f"Applied {len(payload)} name definition(s).")
        elif surface == "tables":
            table_specs = {(item["sheet"], item["name"]): item for item in payload}
            for (sheet_name, table_name), table_spec in table_specs.items():
                sheet_path = _sheet_xml_path(package, sheet_name)
                sheet_xml = package._read_xml(sheet_path)
                table_parts = sheet_xml.find("main:tableParts", NS)
                if table_parts is None:
                    raise ValueError(f"Worksheet {sheet_name} does not expose table parts for package table sync.")
                table_rel = None
                for table_part in table_parts.findall("main:tablePart", NS):
                    rel_id = table_part.attrib.get(f"{{{NS['rel']}}}id")
                    rel = package.sheets[[sheet["name"] for sheet in package.sheets].index(sheet_name)]["rels"].get(rel_id or "")
                    if not rel:
                        continue
                    table_xml = package._read_xml(rel["target"])
                    if table_xml.attrib.get("name", "") == table_name:
                        table_rel = rel
                        break
                if table_rel is None:
                    raise ValueError(f"Package-backed table sync currently requires an existing table: {sheet_name}!{table_name}")
                table_xml = package._read_xml(table_rel["target"])
                headers = [str(value) for value in table_spec.get("headers", [])]
                rows = table_spec.get("rows", [])
                if not headers:
                    raise ValueError(f"Table {table_name} requires headers for package sync.")
                top_left = table_spec.get("topLeft") or table_xml.attrib.get("ref", "").split(":", 1)[0]
                start_row, start_col = _cell_ref_to_row_col(top_left)
                end_row = start_row + len(rows)
                end_col = start_col + len(headers) - 1
                table_ref = f"{_row_col_to_cell_ref(start_row, start_col)}:{_row_col_to_cell_ref(end_row, end_col)}"
                table_xml.attrib["ref"] = table_ref
                table_columns = table_xml.find("main:tableColumns", NS)
                if table_columns is None:
                    table_columns = ET.SubElement(table_xml, f"{{{NS['main']}}}tableColumns")
                for child in list(table_columns):
                    table_columns.remove(child)
                table_columns.attrib["count"] = str(len(headers))
                for index, header in enumerate(headers, start=1):
                    ET.SubElement(
                        table_columns,
                        f"{{{NS['main']}}}tableColumn",
                        {"id": str(index), "name": header},
                    )

                for col_offset, header in enumerate(headers):
                    _apply_cell_value_to_sheet(sheet_xml, _row_col_to_cell_ref(start_row, start_col + col_offset), header)
                for row_offset, row_values in enumerate(rows, start=1):
                    if len(row_values) != len(headers):
                        raise ValueError(f"Table {table_name} row width does not match header width")
                    for col_offset, value in enumerate(row_values):
                        _apply_cell_value_to_sheet(
                            sheet_xml,
                            _row_col_to_cell_ref(start_row + row_offset, start_col + col_offset),
                            value,
                        )
                updates[sheet_path] = _serialize_xml(sheet_xml)
                updates[table_rel["target"]] = _serialize_xml(table_xml)
            messages.append(f"Applied {len(payload)} table definition(s).")
        elif surface == "formulas":
            sheet_groups: dict[str, list[dict[str, Any]]] = {}
            for item in payload:
                sheet_groups.setdefault(item["sheet"], []).append(item)
            for sheet_name, formulas in sheet_groups.items():
                path = _sheet_xml_path(package, sheet_name)
                root = package._read_xml(path)
                sheet_data = root.find("main:sheetData", NS)
                if sheet_data is None:
                    sheet_data = ET.SubElement(root, f"{{{NS['main']}}}sheetData")
                for formula in formulas:
                    row_number, _ = _cell_ref_to_row_col(formula["address"])
                    row = _get_or_create_row(sheet_data, row_number)
                    cell = _get_or_create_cell(row, formula["address"])
                    formula_node = cell.find("main:f", NS)
                    if formula_node is None:
                        formula_node = ET.SubElement(cell, f"{{{NS['main']}}}f")
                    formula_node.text = formula.get("formula", "")
                    kind = formula.get("kind")
                    ref = formula.get("reference")
                    if kind and kind != "normal":
                        formula_node.attrib["t"] = kind
                    else:
                        formula_node.attrib.pop("t", None)
                    if ref:
                        formula_node.attrib["ref"] = ref
                    else:
                        formula_node.attrib.pop("ref", None)
                    if formula.get("value") is not None:
                        _set_text_child(cell, "v", str(formula["value"]))
                updates[path] = _serialize_xml(root)
                messages.append(f"Applied {len(formulas)} formula definition(s) on {sheet_name}.")
        elif surface == "data-validation":
            sheet_groups: dict[str, list[dict[str, Any]]] = {}
            for item in payload:
                sheet_groups.setdefault(item["sheet"], []).append(item)
            for sheet_name, rules in sheet_groups.items():
                path = _sheet_xml_path(package, sheet_name)
                root = package._read_xml(path)
                validations = root.find("main:dataValidations", NS)
                if validations is not None:
                    root.remove(validations)
                if rules:
                    validations = ET.SubElement(root, f"{{{NS['main']}}}dataValidations", {"count": str(len(rules))})
                    for rule in rules:
                        attrs = {
                            "sqref": rule["address"].replace(",", " "),
                            "type": rule.get("type") or "any",
                        }
                        for source, target in (
                            ("operator", "operator"),
                            ("allowBlank", "allowBlank"),
                            ("showInputMessage", "showInputMessage"),
                            ("showErrorMessage", "showErrorMessage"),
                            ("errorStyle", "errorStyle"),
                        ):
                            value = rule.get(source)
                            if value is None:
                                continue
                            attrs[target] = "1" if value is True else "0" if value is False else str(value)
                        node = ET.SubElement(validations, f"{{{NS['main']}}}dataValidation", attrs)
                        if rule.get("formula1") is not None:
                            ET.SubElement(node, f"{{{NS['main']}}}formula1").text = str(rule["formula1"])
                        if rule.get("formula2") is not None:
                            ET.SubElement(node, f"{{{NS['main']}}}formula2").text = str(rule["formula2"])
                updates[path] = _serialize_xml(root)
                messages.append(f"Applied {len(rules)} data-validation rule(s) on {sheet_name}.")
        elif surface == "cf":
            sheet_groups: dict[str, list[dict[str, Any]]] = {}
            for item in payload:
                sheet_groups.setdefault(item["sheet"], []).append(item)
            for sheet_name, rules in sheet_groups.items():
                path = _sheet_xml_path(package, sheet_name)
                root = package._read_xml(path)
                for node in list(root.findall("main:conditionalFormatting", NS)):
                    root.remove(node)
                for rule in sorted(rules, key=lambda entry: (entry.get("priority") or 0, entry.get("id") or "")):
                    raw_type = {
                        "expression": "expression",
                        "cell-value": "cellIs",
                        "unique-values": "uniqueValues",
                        "top10": "top10",
                        "above-average": "aboveAverage",
                        "color-scale": "colorScale",
                        "data-bar": "dataBar",
                        "icon-set": "iconSet",
                    }.get(rule.get("type"), rule.get("rawType") or rule.get("type") or "expression")
                    group = ET.SubElement(root, f"{{{NS['main']}}}conditionalFormatting", {"sqref": rule["address"].replace(",", " ")})
                    attrs = {"type": raw_type}
                    if rule.get("priority") is not None:
                        attrs["priority"] = str(rule["priority"])
                    if rule.get("stopIfTrue") is not None:
                        attrs["stopIfTrue"] = "1" if rule["stopIfTrue"] else "0"
                    if rule.get("operator"):
                        attrs["operator"] = str(rule["operator"])
                    node = ET.SubElement(group, f"{{{NS['main']}}}cfRule", attrs)
                    if rule.get("formula") is not None:
                        ET.SubElement(node, f"{{{NS['main']}}}formula").text = str(rule["formula"])
                    if rule.get("formula2") is not None:
                        ET.SubElement(node, f"{{{NS['main']}}}formula").text = str(rule["formula2"])
                updates[path] = _serialize_xml(root)
                messages.append(f"Applied {len(rules)} conditional-format rule(s) on {sheet_name}.")
        elif surface == "protection":
            workbook_root = package.workbook_xml
            workbook_spec = (payload or {}).get("workbook")
            workbook_node = workbook_root.find("main:workbookProtection", NS)
            if workbook_spec:
                if workbook_node is None:
                    workbook_node = ET.SubElement(workbook_root, f"{{{NS['main']}}}workbookProtection")
                for key, value in workbook_spec.items():
                    if value is None:
                        workbook_node.attrib.pop(key, None)
                    else:
                        workbook_node.attrib[key] = "1" if value else "0"
            elif workbook_node is not None:
                workbook_root.remove(workbook_node)
            updates["xl/workbook.xml"] = _serialize_xml(workbook_root)
            worksheet_specs = {item["sheet"]: item for item in (payload or {}).get("worksheets", [])}
            target_sheets = selectors["sheet"] or set(worksheet_specs)
            for sheet_name in target_sheets:
                path = _sheet_xml_path(package, sheet_name)
                root = package._read_xml(path)
                node = root.find("main:sheetProtection", NS)
                spec = worksheet_specs.get(sheet_name)
                if spec:
                    if node is None:
                        node = ET.SubElement(root, f"{{{NS['main']}}}sheetProtection")
                    for key, value in spec.items():
                        if key == "sheet":
                            continue
                        if value is None:
                            node.attrib.pop(key, None)
                        else:
                            node.attrib[key] = "1" if value else "0"
                elif node is not None:
                    root.remove(node)
                updates[path] = _serialize_xml(root)
            messages.append("Applied workbook and worksheet protection settings.")
        elif surface == "dimensions":
            target_sheets = selectors["sheet"] or {item.get("sheet") for item in (payload or {}).get("sheets", [])}
            dimension_specs = {item["sheet"]: item for item in (payload or {}).get("sheets", [])}
            for sheet_name in sorted(name for name in target_sheets if name):
                path = _sheet_xml_path(package, sheet_name)
                root = package._read_xml(path)
                sheet_data = root.find("main:sheetData", NS)
                if sheet_data is None:
                    sheet_data = ET.SubElement(root, f"{{{NS['main']}}}sheetData")
                spec = dimension_specs.get(sheet_name) or {"rows": [], "columns": []}
                row_specs = {int(item["row"]): item for item in spec.get("rows", []) if item.get("row") is not None}
                for row in list(sheet_data.findall("main:row", NS)):
                    row_number = int(row.attrib.get("r", "0") or "0")
                    row_spec = row_specs.get(row_number)
                    dimension_keys = ("ht", "hidden", "outlineLevel", "collapsed", "customHeight", "s", "customFormat")
                    if row_spec is None:
                        for key in dimension_keys:
                            row.attrib.pop(key, None)
                        continue
                    mapping = {
                        "height": "ht",
                        "hidden": "hidden",
                        "outlineLevel": "outlineLevel",
                        "collapsed": "collapsed",
                        "style": "s",
                        "customHeight": "customHeight",
                        "customFormat": "customFormat",
                    }
                    for source_key, attr_name in mapping.items():
                        value = row_spec.get(source_key)
                        if value is None:
                            row.attrib.pop(attr_name, None)
                        else:
                            row.attrib[attr_name] = "1" if value is True else "0" if value is False else str(value)
                for row_number, row_spec in row_specs.items():
                    row = _get_or_create_row(sheet_data, row_number)
                    mapping = {
                        "height": "ht",
                        "hidden": "hidden",
                        "outlineLevel": "outlineLevel",
                        "collapsed": "collapsed",
                        "style": "s",
                        "customHeight": "customHeight",
                        "customFormat": "customFormat",
                    }
                    for source_key, attr_name in mapping.items():
                        value = row_spec.get(source_key)
                        if value is None:
                            row.attrib.pop(attr_name, None)
                        else:
                            row.attrib[attr_name] = "1" if value is True else "0" if value is False else str(value)

                cols_node = root.find("main:cols", NS)
                if cols_node is not None:
                    root.remove(cols_node)
                column_specs = spec.get("columns", [])
                if column_specs:
                    insert_at = 0
                    sheet_data_node = root.find("main:sheetData", NS)
                    if sheet_data_node is not None:
                        insert_at = list(root).index(sheet_data_node)
                    cols_node = ET.Element(f"{{{NS['main']}}}cols")
                    for column_spec in column_specs:
                        attrs: dict[str, str] = {
                            "min": str(column_spec.get("min", 1)),
                            "max": str(column_spec.get("max", column_spec.get("min", 1))),
                        }
                        for source_key, attr_name in (
                            ("width", "width"),
                            ("hidden", "hidden"),
                            ("bestFit", "bestFit"),
                            ("customWidth", "customWidth"),
                            ("style", "style"),
                            ("outlineLevel", "outlineLevel"),
                            ("collapsed", "collapsed"),
                        ):
                            value = column_spec.get(source_key)
                            if value is None:
                                continue
                            attrs[attr_name] = "1" if value is True else "0" if value is False else str(value)
                        ET.SubElement(cols_node, f"{{{NS['main']}}}col", attrs)
                    root.insert(insert_at, cols_node)
                updates[path] = _serialize_xml(root)
            messages.append("Applied row and column dimension settings.")
        elif surface == "hyperlinks":
            content_types_root = package._read_xml("[Content_Types].xml")
            sheet_groups: dict[str, list[dict[str, Any]]] = {}
            for item in payload:
                sheet_groups.setdefault(item["sheet"], []).append(item)
            target_sheets = selectors["sheet"] or set(sheet_groups)
            for sheet_name in sorted(name for name in target_sheets if name):
                path = _sheet_xml_path(package, sheet_name)
                root = package._read_xml(path)
                hyperlinks_node = root.find("main:hyperlinks", NS)
                if hyperlinks_node is not None:
                    root.remove(hyperlinks_node)
                rels_path = _sheet_rels_path(path)
                rels_root = _relationships_root()
                try:
                    rels_root = package._read_xml(rels_path)
                except KeyError:
                    rels_root = _relationships_root()
                _remove_relationships_by_type(
                    rels_root,
                    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
                )
                links = sheet_groups.get(sheet_name, [])
                if links:
                    hyperlinks_node = ET.SubElement(root, f"{{{NS['main']}}}hyperlinks")
                    for link in links:
                        attrs = {"ref": str(link["address"])}
                        target = link.get("target")
                        if target:
                            rel_id = _upsert_relationship(
                                rels_root,
                                rel_type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
                                target=str(target),
                                target_mode="External",
                            )
                            attrs[f"{{{NS['rel']}}}id"] = rel_id
                        for key in ("location", "display", "tooltip"):
                            value = link.get(key)
                            if value is not None:
                                attrs[key] = str(value)
                        ET.SubElement(hyperlinks_node, f"{{{NS['main']}}}hyperlink", attrs)
                updates[path] = _serialize_xml(root)
                updates[rels_path] = _serialize_xml(rels_root)
            updates["[Content_Types].xml"] = _serialize_xml(content_types_root)
            messages.append(f"Applied {len(payload)} hyperlink definition(s).")
        elif surface == "comments":
            content_types_root = package._read_xml("[Content_Types].xml")
            sheet_groups: dict[str, list[dict[str, Any]]] = {}
            for item in payload:
                sheet_groups.setdefault(item["sheet"], []).append(item)
            target_sheets = selectors["sheet"] or set(sheet_groups)
            for sheet_name in sorted(name for name in target_sheets if name):
                path = _sheet_xml_path(package, sheet_name)
                rels_path = _sheet_rels_path(path)
                try:
                    rels_root = package._read_xml(rels_path)
                except KeyError:
                    rels_root = _relationships_root()
                comments_path = _comments_part_path(path)
                comments_rel_target = f"../{PurePosixPath(comments_path).name}"
                comments = sheet_groups.get(sheet_name, [])
                if comments:
                    rel_id = _upsert_relationship(
                        rels_root,
                        rel_type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments",
                        target=comments_rel_target,
                    )
                    comment_root = ET.Element(f"{{{NS['main']}}}comments")
                    authors_node = ET.SubElement(comment_root, f"{{{NS['main']}}}authors")
                    author_names: list[str] = []
                    for comment in comments:
                        author = comment.get("author") or ""
                        if author not in author_names:
                            author_names.append(author)
                    for author in author_names:
                        author_node = ET.SubElement(authors_node, f"{{{NS['main']}}}author")
                        author_node.text = author
                    comment_list = ET.SubElement(comment_root, f"{{{NS['main']}}}commentList")
                    for comment in comments:
                        author = comment.get("author") or ""
                        comment_node = ET.SubElement(
                            comment_list,
                            f"{{{NS['main']}}}comment",
                            {
                                "ref": str(comment["address"]),
                                "authorId": str(author_names.index(author)),
                            },
                        )
                        text_node = ET.SubElement(comment_node, f"{{{NS['main']}}}text")
                        run_node = ET.SubElement(text_node, f"{{{NS['main']}}}r")
                        t_node = ET.SubElement(run_node, f"{{{NS['main']}}}t")
                        t_node.text = str(comment.get("text") or "")
                    updates[comments_path] = _serialize_xml(comment_root)
                    _ensure_override(
                        content_types_root,
                        f"/{comments_path}",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.comments+xml",
                    )
                else:
                    _remove_relationships_by_type(
                        rels_root,
                        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments",
                    )
                updates[rels_path] = _serialize_xml(rels_root)
            updates["[Content_Types].xml"] = _serialize_xml(content_types_root)
            messages.append(f"Applied {len(payload)} comment definition(s).")
        elif surface == "print":
            workbook_root = package.workbook_xml
            defined_names = workbook_root.find("main:definedNames", NS)
            if defined_names is None:
                defined_names = ET.Element(f"{{{NS['main']}}}definedNames")
                sheets_node = workbook_root.find("main:sheets", NS)
                insert_at = list(workbook_root).index(sheets_node) + 1 if sheets_node is not None else len(list(workbook_root))
                workbook_root.insert(insert_at, defined_names)
            sheet_specs = {item["sheet"]: item for item in (payload or {}).get("sheets", [])}
            target_sheets = selectors["sheet"] or set(sheet_specs)
            for item in list(defined_names):
                name = item.attrib.get("name")
                if name not in {"_xlnm.Print_Area", "_xlnm.Print_Titles"}:
                    continue
                local_sheet_id = item.attrib.get("localSheetId")
                if local_sheet_id is None or not local_sheet_id.isdigit():
                    continue
                if int(local_sheet_id) >= len(package.sheets):
                    continue
                sheet_name = package.sheets[int(local_sheet_id)]["name"]
                if sheet_name in target_sheets:
                    defined_names.remove(item)
            for index, sheet in enumerate(package.sheets):
                sheet_name = sheet["name"]
                if sheet_name not in target_sheets:
                    continue
                spec = sheet_specs.get(sheet_name) or {}
                if spec.get("printArea"):
                    node = ET.SubElement(
                        defined_names,
                        f"{{{NS['main']}}}definedName",
                        {"name": "_xlnm.Print_Area", "localSheetId": str(index)},
                    )
                    node.text = str(spec["printArea"])
                if spec.get("printTitles"):
                    node = ET.SubElement(
                        defined_names,
                        f"{{{NS['main']}}}definedName",
                        {"name": "_xlnm.Print_Titles", "localSheetId": str(index)},
                    )
                    node.text = str(spec["printTitles"])
                path = _sheet_xml_path(package, sheet_name)
                root = package._read_xml(path)
                for node_name, spec_key in (
                    ("pageMargins", "margins"),
                    ("pageSetup", "pageSetup"),
                    ("printOptions", "printOptions"),
                ):
                    node = root.find(f"main:{node_name}", NS)
                    node_spec = spec.get(spec_key)
                    if node_spec:
                        if node is None:
                            node = ET.SubElement(root, f"{{{NS['main']}}}{node_name}")
                        node.attrib.clear()
                        for key, value in node_spec.items():
                            if value is not None:
                                node.attrib[key] = "1" if value is True else "0" if value is False else str(value)
                    elif node is not None:
                        root.remove(node)
                header_footer = root.find("main:headerFooter", NS)
                header_footer_spec = spec.get("headerFooter")
                if header_footer_spec:
                    if header_footer is None:
                        header_footer = ET.SubElement(root, f"{{{NS['main']}}}headerFooter")
                    for child_name in ("oddHeader", "oddFooter", "evenHeader", "evenFooter", "firstHeader", "firstFooter"):
                        _set_text_child(header_footer, child_name, header_footer_spec.get(child_name))
                elif header_footer is not None:
                    root.remove(header_footer)
                updates[path] = _serialize_xml(root)
            updates["xl/workbook.xml"] = _serialize_xml(workbook_root)
            messages.append("Applied print areas, titles, and page layout settings.")
        elif surface == "charts":
            chart_specs = {
                (item.get("sheet"), item.get("name")): item
                for item in (payload or [])
                if isinstance(item, dict) and item.get("sheet") and item.get("name")
            }
            target_sheets = selectors["sheet"] or {sheet for sheet, _ in chart_specs}
            updated_count = 0
            for entry in _chart_part_entries(package):
                sheet_name = entry.get("sheet")
                chart_name = entry.get("name")
                chart_path = entry.get("path")
                if not sheet_name or not chart_name or not chart_path:
                    continue
                if target_sheets and sheet_name not in target_sheets:
                    continue
                spec = chart_specs.get((sheet_name, chart_name))
                if spec is None:
                    continue
                chart_root = package._read_xml(chart_path)
                if _apply_chart_relationship_spec(chart_root, spec):
                    updates[chart_path] = _serialize_xml(chart_root)
                    updated_count += 1
            messages.append(
                f"Applied chart title and series reference updates to {updated_count} existing chart part(s); route chart creation, deletion, and rich formatting to desktop Excel."
            )
        elif surface in {"styles", "themes"}:
            part_specs = (payload or {}).get("parts", []) if isinstance(payload, dict) else []
            if not isinstance(part_specs, list):
                raise ValueError(f"{surface} package payload must contain a parts array")
            updated_count = 0
            for part_spec in part_specs:
                if not isinstance(part_spec, dict):
                    continue
                part_path, content = _validated_package_xml_update(part_spec, surface)
                updates[part_path] = content
                updated_count += 1
            messages.append(f"Applied {updated_count} {surface} package part replacement(s).")
        else:
            raise ValueError(f"Unsupported package push surface: {surface}")
    finally:
        package.close()
    if updates:
        _rewrite_workbook_package(workbook_path, updates)
    return messages


def write_repo_surface_payload(bundle: dict[str, Any], surface: str, payload: Any) -> None:
    artifact_path = _surface_artifact_path(bundle, surface)
    if artifact_path is None:
        return
    _write_json(artifact_path, _wrap_artifact_payload(surface, payload))


def compare_bundle_surfaces(bundle: dict[str, Any], surfaces: list[str], selectors: dict[str, set[str]]) -> dict[str, Any]:
    workbook_payload = build_query_payload(bundle["workbookPath"], surfaces)
    results: list[dict[str, Any]] = []
    for surface in surfaces:
        spec = PACKAGE_SURFACE_SPECS[surface]
        route = _surface_route_payload(surface)
        workbook_surface = _selected_surface_items(surface, workbook_payload.get(spec["queryKey"]), selectors)
        repo_surface = _selected_surface_items(surface, load_repo_surface_payload(bundle, surface), selectors)
        summary = _summarize_diff(surface, repo_surface, workbook_surface)
        results.append(
            {
                "surface": surface,
                "backend": "package",
                "route": route["route"],
                "engineRoute": route,
                "requestedSelectors": {key: sorted(value) for key, value in selectors.items() if value},
                "comparisonAvailable": repo_surface is not None and workbook_surface is not None,
                "strict": summary,
                "normalized": copy.deepcopy(summary),
                "intent": copy.deepcopy(summary),
            }
        )
    return {
        "workbookPath": str(bundle["workbookPath"]),
        "manifestPath": str(bundle["manifestPath"]),
        "backend": "package",
        "surfaces": results,
    }


def plan_bundle_sync(
    bundle: dict[str, Any],
    surfaces: list[str],
    selectors: dict[str, set[str]],
    mode: str,
    state_root: Path,
) -> dict[str, Any]:
    workbook_payload = build_query_payload(bundle["workbookPath"], surfaces)
    plans: list[dict[str, Any]] = []
    for surface in surfaces:
        spec = PACKAGE_SURFACE_SPECS[surface]
        route = _surface_route_payload(surface)
        repo_surface = _selected_surface_items(surface, load_repo_surface_payload(bundle, surface), selectors)
        workbook_surface = _selected_surface_items(surface, workbook_payload.get(spec["queryKey"]), selectors)
        baseline_surface = _selected_surface_items(surface, _load_baseline(state_root, bundle, surface), selectors)
        can_write = bool(spec["writable"])
        if baseline_surface is None:
            merged_surface = repo_surface if mode in {"push", "roundtrip"} else workbook_surface
            conflicts = []
            merge_counts = {"mergedRepo": 0, "preservedWorkbook": 0, "unchanged": 0}
        else:
            merged_surface, conflicts, merge_counts = _merge_surface(surface, baseline_surface, repo_surface, workbook_surface)
        desired_surface = merged_surface if baseline_surface is not None else (repo_surface if mode in {"push", "roundtrip"} else workbook_surface)
        if mode == "pull":
            desired_surface = merged_surface if baseline_surface is not None else workbook_surface
        compare_summary = _summarize_diff(surface, desired_surface, workbook_surface)
        plans.append(
            {
                "surface": surface,
                "backendRequired": route.get("requiresBackend") or route["writeBackend"],
                "backendChosen": "package",
                "route": route["route"],
                "engineRoute": route,
                "canRead": True,
                "canWrite": can_write and not route.get("requiresBackend"),
                "comparison": compare_summary,
                "plannedWrites": compare_summary["counts"]["changed"] + compare_summary["counts"]["repoOnly"] + compare_summary["counts"]["workbookOnly"],
                "unsupportedReason": None if (can_write and not route.get("requiresBackend")) else spec.get("unsupportedReason") or "Route this surface to desktop Excel for write-back.",
                "merge": {
                    "baselinePresent": baseline_surface is not None,
                    "counts": merge_counts,
                    "conflicts": conflicts,
                },
                "statePath": str(_state_surface_path(state_root, bundle, surface)),
            }
        )
    return {
        "workbookPath": str(bundle["workbookPath"]),
        "manifestPath": str(bundle["manifestPath"]),
        "mode": mode,
        "backend": "package",
        "selectors": {key: sorted(value) for key, value in selectors.items() if value},
        "surfaces": plans,
    }


def sync_bundle_surfaces(
    bundle: dict[str, Any],
    surfaces: list[str],
    selectors: dict[str, set[str]],
    mode: str,
    state_root: Path,
    apply: bool,
) -> dict[str, Any]:
    workbook_payload = build_query_payload(bundle["workbookPath"], surfaces)
    results: list[dict[str, Any]] = []
    for surface in surfaces:
        spec = PACKAGE_SURFACE_SPECS[surface]
        route = _surface_route_payload(surface)
        repo_surface = _selected_surface_items(surface, load_repo_surface_payload(bundle, surface), selectors)
        workbook_surface = _selected_surface_items(surface, workbook_payload.get(spec["queryKey"]), selectors)
        baseline_surface = _selected_surface_items(surface, _load_baseline(state_root, bundle, surface), selectors)
        if baseline_surface is None:
            merged_surface = repo_surface if mode in {"push", "roundtrip"} else workbook_surface
            conflicts = []
            merge_counts = {"mergedRepo": 0, "preservedWorkbook": 0, "unchanged": 0}
        else:
            merged_surface, conflicts, merge_counts = _merge_surface(surface, baseline_surface, repo_surface, workbook_surface)
        if baseline_surface is None:
            desired_surface = repo_surface if mode in {"push", "roundtrip"} else workbook_surface
        else:
            desired_surface = merged_surface
        if mode == "pull":
            desired_surface = merged_surface if baseline_surface is not None else workbook_surface
        workbook_diff = _summarize_diff(surface, desired_surface, workbook_surface)
        repo_diff = _summarize_diff(surface, desired_surface, repo_surface)
        status = "dry-run"
        messages: list[str] = []
        if conflicts:
            status = "conflicts"
        elif route.get("requiresBackend") and mode in {"push", "roundtrip"} and workbook_diff["match"] is False:
            status = "requires-desktop"
            messages.append(f"{surface} writes require the {route['requiresBackend']} backend; package mode produced a safe plan only.")
        elif not spec["writable"] and mode in {"push", "roundtrip"} and workbook_diff["match"] is False:
            status = "requires-desktop"
            messages.append(spec.get("unsupportedReason") or f"{surface} writes are not available in package mode.")
        elif apply:
            if mode in {"push", "roundtrip"} and spec["writable"] and not workbook_diff["match"]:
                messages.extend(apply_package_surface_push(bundle["workbookPath"], surface, desired_surface, selectors))
            if mode in {"pull", "roundtrip"} and repo_diff["match"] is False:
                write_repo_surface_payload(bundle, surface, desired_surface)
                messages.append(f"Updated repo artifact for {surface}.")
            _write_baseline(state_root, bundle, surface, desired_surface)
            status = "applied"
        results.append(
            {
                "surface": surface,
                "status": status,
                "backend": "package",
                "route": route["route"],
                "engineRoute": route,
                "mode": mode,
                "messages": messages,
                "merge": {
                    "baselinePresent": baseline_surface is not None,
                    "counts": merge_counts,
                    "conflicts": conflicts,
                },
                "plannedWorkbookWrites": workbook_diff["counts"],
                "plannedRepoWrites": repo_diff["counts"],
                "unsupportedReason": None if (spec["writable"] and not route.get("requiresBackend")) else spec.get("unsupportedReason") or "Route this surface to desktop Excel for write-back.",
            }
        )
    return {
        "workbookPath": str(bundle["workbookPath"]),
        "manifestPath": str(bundle["manifestPath"]),
        "mode": mode,
        "apply": apply,
        "backend": "package",
        "selectors": {key: sorted(value) for key, value in selectors.items() if value},
        "surfaces": results,
    }


def apply_audit_mutation(workbook_path: Path) -> dict[str, Any]:
    workbook_path = workbook_path.resolve()
    with zipfile.ZipFile(workbook_path, "r") as source:
        workbook_xml = source.read("xl/workbook.xml")
    root = ET.fromstring(workbook_xml)
    defined_names = root.find("main:definedNames", NS)
    if defined_names is None:
        defined_names = ET.Element(f"{{{NS['main']}}}definedNames")
        sheets = root.find("main:sheets", NS)
        insert_at = list(root).index(sheets) + 1 if sheets is not None else len(list(root))
        root.insert(insert_at, defined_names)
    for item in list(defined_names):
        if item.attrib.get("name") == "ExcelSyncAuditMutation":
            defined_names.remove(item)
    entry = ET.SubElement(defined_names, f"{{{NS['main']}}}definedName", {"name": "ExcelSyncAuditMutation"})
    entry.text = '="ExcelSyncAuditPackageFallback"'
    updated_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    _rewrite_workbook_package(workbook_path, {"xl/workbook.xml": updated_xml})
    return {
        "ran": True,
        "packageFallback": True,
        "workbook": str(workbook_path),
        "createdSheet": None,
        "createdTables": [],
        "createdQueries": [],
        "conditionalFormattingCount": 0,
        "scenarios": [
            {
                "name": "package-defined-name-fallback",
                "status": "completed",
                "details": {
                    "name": "ExcelSyncAuditMutation",
                    "refersTo": '="ExcelSyncAuditPackageFallback"',
                },
            }
        ],
        "phaseDurationsMs": {},
    }


def run_direct_package_command(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "workbook-capabilities":
        workbook_path = Path(args.workbook_path)
        payload = {
            "backend": "multi-engine",
            "workbookPath": str(workbook_path.resolve()),
            "capabilities": _workbook_engine_capabilities(workbook_path),
        }
        if getattr(args, "deep", False):
            payload["capabilityLedger"] = _capability_ledger_for_workbook(workbook_path)
        return payload
    if args.command == "workbook-inspect":
        workbook_path = Path(args.workbook_path)
        surfaces = normalize_surfaces(getattr(args, "surface", ""))
        if not surfaces:
            return build_inventory_payload(workbook_path)
        return build_inspection_payload(build_query_payload(workbook_path, surfaces))
    if args.command == "workbook-diff":
        return compare_workbook_payloads(Path(args.workbook_path), Path(args.other_workbook_path), normalize_surfaces(getattr(args, "surface", "")))
    if args.command == "workbook-create":
        spec = {}
        if getattr(args, "spec_json", None):
            spec = json.loads(args.spec_json)
        elif getattr(args, "spec_file", None):
            spec = json.loads(Path(args.spec_file).read_text(encoding="utf-8"))
        return create_blank_workbook(Path(args.workbook_path), spec)
    if args.command == "manifest-validate":
        return validate_manifest_file(Path(args.manifest_path), check_files=False)
    if args.command == "manifest-doctor":
        return validate_manifest_file(Path(args.manifest_path), check_files=True)
    if args.command == "manifest-migrate":
        manifest_path = Path(args.manifest_path)
        migrated = migrate_manifest_payload(manifest_path)
        wrote_path = None
        if getattr(args, "apply", False):
            manifest_path.write_text(json.dumps(migrated, indent=2) + "\n", encoding="utf-8")
            wrote_path = str(manifest_path.resolve())
        return {
            "manifestPath": str(manifest_path.resolve()),
            "applied": bool(getattr(args, "apply", False)),
            "wrotePath": wrote_path,
            "migratedManifest": migrated,
        }

    workbook_path = Path(args.workbook_path)
    package = WorkbookPackage(workbook_path)
    try:
        if args.command == "sheet-list":
            return {
                "backend": "package",
                "workbookPath": str(workbook_path.resolve()),
                "sheets": package.parse_sheets(),
            }
        if args.command == "table-list":
            return {
                "backend": "package",
                "workbookPath": str(workbook_path.resolve()),
                "tables": package.parse_tables(),
            }
        if args.command == "table-read":
            tables = package.parse_tables()
            selected = next((item for item in tables if item["name"] == args.table_name and (not args.sheet or item["sheet"] == args.sheet)), None)
            if selected is None:
                raise ValueError(f"Unknown table: {args.table_name}")
            return {"backend": "package", "workbookPath": str(workbook_path.resolve()), "table": selected}
        if args.command == "name-list":
            return {
                "backend": "package",
                "workbookPath": str(workbook_path.resolve()),
                "names": package.parse_names(),
            }
        if args.command == "query-list":
            pq = package.parse_power_query()
            return {
                "backend": "package",
                "workbookPath": str(workbook_path.resolve()),
                "queries": pq["queries"],
                "connections": pq["connections"],
                "model": {"modelTables": pq["modelTables"]},
            }
        if args.command == "dimension-get":
            return {"backend": "package", "workbookPath": str(workbook_path.resolve()), "dimensions": package.parse_dimensions()}
        if args.command == "hyperlink-list":
            return {"backend": "package", "workbookPath": str(workbook_path.resolve()), "hyperlinks": package.parse_hyperlinks()}
        if args.command == "comment-list":
            return {"backend": "package", "workbookPath": str(workbook_path.resolve()), "comments": package.parse_comments()}
        if args.command == "print-get":
            return {"backend": "package", "workbookPath": str(workbook_path.resolve()), "print": package.parse_print_settings()}
        if args.command == "formula-list":
            return {"backend": "package", "workbookPath": str(workbook_path.resolve()), "formulas": package.parse_formulas()}
        if args.command == "validation-list":
            return {"backend": "package", "workbookPath": str(workbook_path.resolve()), "dataValidation": package.parse_data_validation()}
        if args.command == "protection-get":
            return {"backend": "package", "workbookPath": str(workbook_path.resolve()), "protection": package.parse_protection()}
        if args.command == "cell-get":
            return {
                "backend": "package",
                "workbookPath": str(workbook_path.resolve()),
                "cell": package.get_cell_payload(args.sheet, args.address),
            }
        if args.command == "range-get":
            return {
                "backend": "package",
                "workbookPath": str(workbook_path.resolve()),
                "range": package.get_range_payload(args.sheet, args.range_ref),
            }
    finally:
        package.close()

    if args.command == "sheet-create":
        return apply_direct_sheet_create(workbook_path, args.sheet)
    if args.command == "sheet-hide":
        return apply_direct_sheet_visibility(workbook_path, args.sheet, "hidden")
    if args.command == "sheet-unhide":
        return apply_direct_sheet_visibility(workbook_path, args.sheet, "visible")
    if args.command == "sheet-very-hide":
        return apply_direct_sheet_visibility(workbook_path, args.sheet, "veryHidden")
    if args.command == "sheet-reorder":
        return apply_direct_sheet_reorder(workbook_path, args.sheet)
    if args.command == "sheet-delete":
        return apply_direct_sheet_delete(workbook_path, args.sheet, bool(args.destructive))
    if args.command == "name-set":
        return apply_direct_names(
            workbook_path,
            [{"name": args.name, "refersTo": args.refers_to, "hidden": args.hidden}],
        )
    if args.command == "name-delete":
        return apply_direct_names(workbook_path, [{"name": args.name, "delete": True}])
    if args.command == "cell-set":
        return apply_direct_cells(
            workbook_path,
            args.sheet,
            [{"address": args.address, "value": json.loads(args.value_json)}],
        )
    if args.command == "range-set":
        values = json.loads(args.values_json)
        start_row, start_col, end_row, end_col = _range_ref_to_bounds(args.range_ref.replace("$", ""))
        expected_rows = end_row - start_row + 1
        expected_cols = end_col - start_col + 1
        if len(values) != expected_rows or any(len(row) != expected_cols for row in values):
            raise ValueError("values-json shape does not match range dimensions")
        assignments = []
        for row_offset, row_values in enumerate(values):
            for col_offset, value in enumerate(row_values):
                assignments.append(
                    {
                        "address": _row_col_to_cell_ref(start_row + row_offset, start_col + col_offset),
                        "value": value,
                    }
                )
        return apply_direct_cells(workbook_path, args.sheet, assignments)
    raise AssertionError(f"unsupported direct command: {args.command}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    query_parser = subparsers.add_parser("query")
    query_parser.add_argument("--workbook-path", required=True)
    query_parser.add_argument("--surface", default="")

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--workbook-path", required=True)
    inspect_parser.add_argument("--surface", default="")

    inspect_lite_parser = subparsers.add_parser("inspect-lite")
    inspect_lite_parser.add_argument("--workbook-path", required=True)

    bootstrap_parser = subparsers.add_parser("bootstrap")
    bootstrap_parser.add_argument("--workbook-path", required=True)
    bootstrap_parser.add_argument("--surface", default="")
    bootstrap_parser.add_argument("--output-dir", required=True)
    bootstrap_parser.add_argument("--manifest-path")

    mutate_parser = subparsers.add_parser("mutate-audit")
    mutate_parser.add_argument("--workbook-path", required=True)

    workbook_capabilities_parser = subparsers.add_parser("workbook-capabilities")
    workbook_capabilities_parser.add_argument("--workbook-path", required=True)
    workbook_capabilities_parser.add_argument("--deep", action="store_true")

    workbook_inspect_parser = subparsers.add_parser("workbook-inspect")
    workbook_inspect_parser.add_argument("--workbook-path", required=True)
    workbook_inspect_parser.add_argument("--surface", default="")

    workbook_create_parser = subparsers.add_parser("workbook-create")
    workbook_create_parser.add_argument("--workbook-path", required=True)
    workbook_create_parser.add_argument("--spec-json")
    workbook_create_parser.add_argument("--spec-file")

    workbook_diff_parser = subparsers.add_parser("workbook-diff")
    workbook_diff_parser.add_argument("--workbook-path", required=True)
    workbook_diff_parser.add_argument("--other-workbook-path", required=True)
    workbook_diff_parser.add_argument("--surface", default="")

    manifest_validate_parser = subparsers.add_parser("manifest-validate")
    manifest_validate_parser.add_argument("--manifest-path", required=True)

    manifest_doctor_parser = subparsers.add_parser("manifest-doctor")
    manifest_doctor_parser.add_argument("--manifest-path", required=True)

    manifest_migrate_parser = subparsers.add_parser("manifest-migrate")
    manifest_migrate_parser.add_argument("--manifest-path", required=True)
    manifest_migrate_parser.add_argument("--apply", action="store_true")

    sheet_list_parser = subparsers.add_parser("sheet-list")
    sheet_list_parser.add_argument("--workbook-path", required=True)

    sheet_create_parser = subparsers.add_parser("sheet-create")
    sheet_create_parser.add_argument("--workbook-path", required=True)
    sheet_create_parser.add_argument("--sheet", required=True)

    sheet_hide_parser = subparsers.add_parser("sheet-hide")
    sheet_hide_parser.add_argument("--workbook-path", required=True)
    sheet_hide_parser.add_argument("--sheet", required=True)

    sheet_unhide_parser = subparsers.add_parser("sheet-unhide")
    sheet_unhide_parser.add_argument("--workbook-path", required=True)
    sheet_unhide_parser.add_argument("--sheet", required=True)

    sheet_very_hide_parser = subparsers.add_parser("sheet-very-hide")
    sheet_very_hide_parser.add_argument("--workbook-path", required=True)
    sheet_very_hide_parser.add_argument("--sheet", required=True)

    sheet_reorder_parser = subparsers.add_parser("sheet-reorder")
    sheet_reorder_parser.add_argument("--workbook-path", required=True)
    sheet_reorder_parser.add_argument("--sheet", action="append", required=True)

    sheet_delete_parser = subparsers.add_parser("sheet-delete")
    sheet_delete_parser.add_argument("--workbook-path", required=True)
    sheet_delete_parser.add_argument("--sheet", required=True)
    sheet_delete_parser.add_argument("--destructive", action="store_true")

    name_list_parser = subparsers.add_parser("name-list")
    name_list_parser.add_argument("--workbook-path", required=True)

    name_set_parser = subparsers.add_parser("name-set")
    name_set_parser.add_argument("--workbook-path", required=True)
    name_set_parser.add_argument("--name", required=True)
    name_set_parser.add_argument("--refers-to", required=True)
    name_set_parser.add_argument("--hidden", action="store_true")

    name_delete_parser = subparsers.add_parser("name-delete")
    name_delete_parser.add_argument("--workbook-path", required=True)
    name_delete_parser.add_argument("--name", required=True)

    table_list_parser = subparsers.add_parser("table-list")
    table_list_parser.add_argument("--workbook-path", required=True)

    table_read_parser = subparsers.add_parser("table-read")
    table_read_parser.add_argument("--workbook-path", required=True)
    table_read_parser.add_argument("--table-name", "--table", dest="table_name", required=True)
    table_read_parser.add_argument("--sheet")

    query_list_parser = subparsers.add_parser("query-list")
    query_list_parser.add_argument("--workbook-path", required=True)

    dimension_get_parser = subparsers.add_parser("dimension-get")
    dimension_get_parser.add_argument("--workbook-path", required=True)

    hyperlink_list_parser = subparsers.add_parser("hyperlink-list")
    hyperlink_list_parser.add_argument("--workbook-path", required=True)

    comment_list_parser = subparsers.add_parser("comment-list")
    comment_list_parser.add_argument("--workbook-path", required=True)

    print_get_parser = subparsers.add_parser("print-get")
    print_get_parser.add_argument("--workbook-path", required=True)

    formula_list_parser = subparsers.add_parser("formula-list")
    formula_list_parser.add_argument("--workbook-path", required=True)

    validation_list_parser = subparsers.add_parser("validation-list")
    validation_list_parser.add_argument("--workbook-path", required=True)

    protection_get_parser = subparsers.add_parser("protection-get")
    protection_get_parser.add_argument("--workbook-path", required=True)

    cell_get_parser = subparsers.add_parser("cell-get")
    cell_get_parser.add_argument("--workbook-path", required=True)
    cell_get_parser.add_argument("--sheet", required=True)
    cell_get_parser.add_argument("--address", required=True)

    cell_set_parser = subparsers.add_parser("cell-set")
    cell_set_parser.add_argument("--workbook-path", required=True)
    cell_set_parser.add_argument("--sheet", required=True)
    cell_set_parser.add_argument("--address", required=True)
    cell_set_parser.add_argument("--value-json", required=True)

    range_get_parser = subparsers.add_parser("range-get")
    range_get_parser.add_argument("--workbook-path", required=True)
    range_get_parser.add_argument("--sheet", required=True)
    range_get_parser.add_argument("--range-ref", required=True)

    range_set_parser = subparsers.add_parser("range-set")
    range_set_parser.add_argument("--workbook-path", required=True)
    range_set_parser.add_argument("--sheet", required=True)
    range_set_parser.add_argument("--range-ref", required=True)
    range_set_parser.add_argument("--values-json", required=True)

    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--manifest-path", required=True)
    plan_parser.add_argument("--workbook-path")
    plan_parser.add_argument("--surface", default="all-supported")
    plan_parser.add_argument("--mode", choices=("push", "pull", "roundtrip"), default="push")
    plan_parser.add_argument("--state-root")
    plan_parser.add_argument("--sheet", action="append", default=[])
    plan_parser.add_argument("--table", action="append", default=[])
    plan_parser.add_argument("--name", action="append", default=[])
    plan_parser.add_argument("--name-prefix", action="append", default=[])
    plan_parser.add_argument("--query-name", action="append", default=[])

    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("--manifest-path", required=True)
    compare_parser.add_argument("--workbook-path")
    compare_parser.add_argument("--surface", default="all-supported")
    compare_parser.add_argument("--sheet", action="append", default=[])
    compare_parser.add_argument("--table", action="append", default=[])
    compare_parser.add_argument("--name", action="append", default=[])
    compare_parser.add_argument("--name-prefix", action="append", default=[])
    compare_parser.add_argument("--query-name", action="append", default=[])

    sync_parser = subparsers.add_parser("sync")
    sync_parser.add_argument("--manifest-path", required=True)
    sync_parser.add_argument("--workbook-path")
    sync_parser.add_argument("--surface", default="all-supported")
    sync_parser.add_argument("--mode", choices=("push", "pull", "roundtrip"), default="push")
    sync_parser.add_argument("--apply", action="store_true")
    sync_parser.add_argument("--state-root")
    sync_parser.add_argument("--sheet", action="append", default=[])
    sync_parser.add_argument("--table", action="append", default=[])
    sync_parser.add_argument("--name", action="append", default=[])
    sync_parser.add_argument("--name-prefix", action="append", default=[])
    sync_parser.add_argument("--query-name", action="append", default=[])

    args = parser.parse_args(argv)
    if args.command in {
        "sheet-list",
        "sheet-create",
        "sheet-hide",
        "sheet-unhide",
        "sheet-very-hide",
        "sheet-reorder",
        "sheet-delete",
        "workbook-capabilities",
        "workbook-inspect",
        "workbook-create",
        "workbook-diff",
        "manifest-validate",
        "manifest-doctor",
        "manifest-migrate",
        "name-list",
        "name-set",
        "name-delete",
        "table-list",
        "table-read",
        "query-list",
        "dimension-get",
        "hyperlink-list",
        "comment-list",
        "print-get",
        "formula-list",
        "validation-list",
        "protection-get",
        "cell-get",
        "cell-set",
        "range-get",
        "range-set",
    }:
        payload = run_direct_package_command(args)
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    if args.command in {"plan", "compare", "sync"}:
        manifest_path = Path(args.manifest_path)
        workbook_override = Path(args.workbook_path) if getattr(args, "workbook_path", None) else None
        bundle = load_sync_manifest(manifest_path, workbook_override)
        selectors = {
            "sheet": {item for item in getattr(args, "sheet", []) if item},
            "table": {item for item in getattr(args, "table", []) if item},
            "name": {item for item in getattr(args, "name", []) if item},
            "name-prefix": {item for item in getattr(args, "name_prefix", []) if item},
            "query": {item for item in getattr(args, "query_name", []) if item},
        }
        surfaces = _normalize_surface_set(getattr(args, "surface", ""), bundle["manifest"])
        state_root = Path(args.state_root).resolve() if getattr(args, "state_root", None) else (bundle["manifestRoot"] / ".excel-sync" / "state")
        if args.command == "plan":
            payload = plan_bundle_sync(bundle, surfaces, selectors, args.mode, state_root)
        elif args.command == "compare":
            payload = compare_bundle_surfaces(bundle, surfaces, selectors)
        else:
            payload = sync_bundle_surfaces(bundle, surfaces, selectors, args.mode, state_root, args.apply)
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    workbook_path = Path(args.workbook_path)
    surfaces = normalize_surfaces(getattr(args, "surface", ""))
    if args.command == "query":
        payload = build_query_payload(workbook_path, surfaces)
    elif args.command == "inspect":
        if surfaces:
            payload = build_inspection_payload(build_query_payload(workbook_path, surfaces))
        else:
            payload = build_inventory_payload(workbook_path)
    elif args.command == "inspect-lite":
        payload = build_inventory_payload(workbook_path)
    elif args.command == "mutate-audit":
        payload = apply_audit_mutation(workbook_path)
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

