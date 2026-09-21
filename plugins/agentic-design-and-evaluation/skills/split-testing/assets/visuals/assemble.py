#!/usr/bin/env python3
"""Package caller-owned HTML, CSS, JavaScript, JSON, and local assets offline."""

from __future__ import annotations

import argparse
import base64
import html
from html.parser import HTMLParser
import json
import mimetypes
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET


class PackagingError(Exception):
    """An actionable input or output error, without a normal traceback."""


ASSET_TOKEN = re.compile(r"\{\{asset:([^{}]+)\}\}")
NAME = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]*\Z")
CSS_WHITESPACE = " \t\n\r\f"
URL_C0_AND_SPACE = "".join(chr(code) for code in range(0x21))
# SVG presentation attributes use CSS property-value syntax (SVG 2, section
# 6.6). Inspect resource-bearing properties, not arbitrary metadata or path
# data. Include SVG 1.1's color-profile and marker shorthand for older exports.
SVG_RESOURCE_PRESENTATION_ATTRIBUTES = {
    "clip-path", "color-profile", "cursor", "fill", "filter", "marker",
    "marker-end", "marker-mid", "marker-start", "mask", "stroke",
}
CSP = "; ".join(
    (
        "default-src 'none'",
        "script-src data:",
        "worker-src blob:",
        "style-src 'unsafe-inline' data:",
        "img-src data:",
        "font-src data:",
        "media-src data:",
        "connect-src 'none'",
        "object-src 'none'",
        "frame-src 'none'",
        "base-uri 'none'",
        "form-action 'none'",
    )
)


def data_url(content: bytes, media_type: str) -> str:
    return f"data:{media_type};base64,{base64.b64encode(content).decode('ascii')}"


def read_text(filename: Path) -> str:
    return filename.read_text(encoding="utf-8")


def resource(reference: str, source: str, *, navigation: bool = False) -> None:
    """Require embedded dependencies; ordinary external citation links may remain."""
    # URL parsing trims ASCII C0 controls and space. Unicode whitespace remains
    # part of a URL and must not turn a relative path into an embedded scheme.
    value = reference.strip(URL_C0_AND_SPACE)
    if value.startswith("#"):
        return
    if value.lower().startswith("data:"):
        return
    if navigation and urlsplit(value).scheme.lower() in {"https", "http", "mailto", "tel"}:
        return
    raise PackagingError(
        f"{source}: non-embedded reference {reference!r}; use an asset token or a document fragment"
    )


def css_escape(text: str, index: int) -> tuple[str, int]:
    """Decode one CSS escape, including escaped URL function identifiers."""
    index += 1
    if index >= len(text):
        raise PackagingError("CSS ends inside an escape")
    match = re.match(r"[0-9A-Fa-f]{1,6}", text[index:])
    if match:
        code = int(match.group(), 16)
        index += len(match.group())
        if index < len(text) and text[index] in CSS_WHITESPACE:
            if text[index:index + 2] == "\r\n":
                index += 1
            index += 1
        return chr(code) if 0 < code <= 0x10FFFF else "\ufffd", index
    if text[index:index + 2] == "\r\n":
        return "", index + 2
    return ("" if text[index] in "\r\n\f" else text[index]), index + 1


def css_string(text: str, index: int) -> tuple[str, int]:
    quote = text[index]
    index += 1
    result = []
    while index < len(text):
        if text[index] == quote:
            return "".join(result), index + 1
        if text[index] == "\\":
            value, index = css_escape(text, index)
            result.append(value)
        else:
            result.append(text[index])
            index += 1
    raise PackagingError("CSS ends inside a string")


def css_identifier(text: str, index: int) -> tuple[str, int]:
    result = []
    while index < len(text):
        if text[index] == "\\":
            value, index = css_escape(text, index)
            result.append(value)
        elif text[index].isalnum() or text[index] in "_-":
            result.append(text[index])
            index += 1
        else:
            break
    return "".join(result).lower(), index


def validate_css(text: str, source: str) -> None:
    """Inspect declared resource syntax, without claiming to validate all CSS."""
    index = 0
    while index < len(text):
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise PackagingError(f"{source}: CSS ends inside a comment")
            index = end + 2
        elif text[index] in "\"'":
            _, index = css_string(text, index)
        elif text[index] == "@":
            identifier, index = css_identifier(text, index + 1)
            if identifier == "import":
                raise PackagingError(f"{source}: CSS @import is unsupported; supply each stylesheet with --style")
        elif text[index].isalpha() or text[index] in "_-\\":
            identifier, index = css_identifier(text, index)
            after = index
            while after < len(text) and text[after] in CSS_WHITESPACE:
                after += 1
            if after >= len(text) or text[after] != "(":
                continue
            if identifier in {"image-set", "-webkit-image-set", "image", "src"}:
                raise PackagingError(f"{source}: CSS {identifier}() is unsupported; use url() with embedded assets")
            if identifier != "url":
                continue
            index = after + 1
            while index < len(text) and text[index] in CSS_WHITESPACE:
                index += 1
            if index < len(text) and text[index] in "\"'":
                reference, index = css_string(text, index)
                while index < len(text) and text[index] in CSS_WHITESPACE:
                    index += 1
            else:
                parts = []
                while index < len(text) and text[index] != ")":
                    if text[index] == "\\":
                        value, index = css_escape(text, index)
                        parts.append(value)
                    else:
                        parts.append(text[index])
                        index += 1
                reference = "".join(parts).strip(CSS_WHITESPACE)
            if index >= len(text) or text[index] != ")":
                raise PackagingError(f"{source}: malformed CSS url()")
            resource(reference, source)
            index += 1
        else:
            index += 1


class BodyValidator(HTMLParser):
    forbidden = {"html", "head", "body", "base", "meta", "title", "script", "style", "link", "iframe", "object", "embed", "plaintext", "xmp", "noembed", "noframes"}
    void = {"area", "br", "col", "hr", "img", "input", "param", "source", "track", "wbr"}

    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self.source = source
        self.ids: set[str] = set()
        self.features: set[str] = set()
        self.elements: list[tuple[str, str]] = []

    def namespace(self, tag: str) -> str:
        namespace = "html"
        if self.elements:
            parent, namespace = self.elements[-1]
            # SVG accessibility text and foreignObject are HTML integration
            # points: their child elements return to HTML parsing rules.
            if namespace == "svg" and parent in {"foreignobject", "desc", "title"}:
                namespace = "html"
        if namespace == "html" and tag == "svg":
            return "svg"
        return namespace

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        namespace = self.namespace(tag)
        if tag in self.forbidden and (tag, namespace) != ("title", "svg"):
            raise PackagingError(f"{self.source}: <{tag}> is unsupported in a body fragment; supply scripts, styles, and data through their CLI options")
        for name, value in attrs:
            if value is None:
                continue
            if name == 'data-av-requires':
                self.features.update(token for token in re.split(r'[ \t\n\r\f]+', value.strip()) if token)
            if name.lower().startswith("on"):
                raise PackagingError(f"{self.source}: event attribute {name} is unsupported; attach listeners in a --script file")
            if name == "id":
                if value in self.ids:
                    raise PackagingError(f"{self.source}: duplicate HTML id {value!r}")
                self.ids.add(value)
            if name == "style":
                validate_css(value, f"{self.source}: style attribute")
            if namespace == "svg" and name in SVG_RESOURCE_PRESENTATION_ATTRIBUTES:
                validate_css(value, f"{self.source}: {tag}[{name}]")
            if name == "srcset":
                raise PackagingError(f"{self.source}: srcset is unsupported; use a single embedded src")
            if name in {"src", "poster", "background", "href", "xlink:href"}:
                resource(value, f"{self.source}: {tag}[{name}]", navigation=tag in {"a", "area"} and name == "href")
            if name in {"action", "formaction", "ping"} and value:
                raise PackagingError(f"{self.source}: {name} would require navigation or network activity; handle report interactions in a --script file")
        if namespace != "html" or tag not in self.void:
            self.elements.append((tag, namespace))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"textarea", "noscript"}:
            raise PackagingError(f"{self.source}: <{tag}/> does not self-close in HTML; provide its explicit closing tag")
        previous_depth = len(self.elements)
        self.handle_starttag(tag, attrs)
        if len(self.elements) > previous_depth:
            self.elements.pop()

    def handle_endtag(self, tag: str) -> None:
        svg_title = tag == "title" and self.elements and self.elements[-1] == ("title", "svg")
        if tag in self.forbidden and not svg_title:
            raise PackagingError(f"{self.source}: </{tag}> is unsupported in a body fragment")
        if not self.elements or self.elements[-1][0] != tag:
            raise PackagingError(f"{self.source}: unmatched </{tag}>; use explicitly balanced HTML in the body fragment")
        self.elements.pop()

    def handle_decl(self, decl: str) -> None:
        raise PackagingError(f"{self.source}: document declarations are unsupported in a body fragment")

    def finish(self) -> None:
        if "<" in self.rawdata:
            raise PackagingError(f"{self.source}: incomplete HTML tag or comment")
        self.close()
        if self.elements:
            raise PackagingError(f"{self.source}: unclosed <{self.elements[-1][0]}>; use explicitly balanced HTML in the body fragment")


def validate_svg(content: bytes, source: str) -> None:
    """An SVG asset must already be self-contained; its bytes remain unchanged."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as error:
        raise PackagingError(f"{source}: invalid SVG: {error}") from None
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1].lower()
        if tag in {"script", "foreignobject", "iframe", "object", "embed"}:
            raise PackagingError(f"{source}: active SVG element {tag!r} is unsupported; use a self-contained image")
        if tag == "style":
            validate_css("".join(element.itertext()), source)
        for key, value in element.attrib.items():
            name = key.rsplit("}", 1)[-1].lower()
            if name.startswith("on"):
                raise PackagingError(f"{source}: SVG event attributes are unsupported")
            if name in {"src", "href"}:
                resource(value, source, navigation=tag == "a")
            if name in SVG_RESOURCE_PRESENTATION_ATTRIBUTES or "url(" in value.lower() or "\\" in value or name == "style":
                validate_css(value, source)


def named_paths(values: list[str], option: str) -> dict[str, Path]:
    result = {}
    for value in values:
        name, separator, filename = value.partition("=")
        if not separator or not NAME.fullmatch(name) or not filename:
            raise PackagingError(f"{option} expects NAME=FILE, with a name beginning with a letter")
        if name in result:
            raise PackagingError(f"{option}: duplicate name {name!r}")
        result[name] = Path(filename)
    return result


def json_content(text: str, source: str) -> str:
    def invalid_constant(value: str) -> None:
        raise ValueError(f"non-JSON number {value}")

    def unique_keys(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate object key {key!r}")
            result[key] = value
        return result

    try:
        # Validate without reserializing or rounding numeric literals.
        json.loads(text, parse_int=str, parse_float=str, parse_constant=invalid_constant, object_pairs_hook=unique_keys)
    except (ValueError, RecursionError) as error:
        raise PackagingError(f"{source}: invalid JSON: {error}") from None
    return text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def assemble(args: argparse.Namespace) -> str:
    asset_paths = named_paths(args.asset, "--asset")
    data_paths = named_paths(args.data, "--data")
    inputs = [args.body, *args.style, *args.script, *asset_paths.values(), *data_paths.values()]
    if args.output.resolve() in {filename.resolve() for filename in inputs}:
        raise PackagingError("output would overwrite an input; choose a separate HTML output path")
    assets = {}
    for name, filename in asset_paths.items():
        content = filename.read_bytes()
        media_type = mimetypes.guess_type(filename.name)[0] or "application/octet-stream"
        if media_type == "image/svg+xml":
            validate_svg(content, str(filename))
        assets[name] = data_url(content, media_type)
    used_assets: set[str] = set()

    def expand(text: str, source: str) -> str:
        def substitute(match: re.Match) -> str:
            name = match.group(1)
            if name not in assets:
                raise PackagingError(f"{source}: asset {name!r} is undeclared; supply --asset {name}=FILE")
            used_assets.add(name)
            return assets[name]
        return ASSET_TOKEN.sub(substitute, text)

    body = expand(read_text(args.body), str(args.body))
    validator = BodyValidator(str(args.body))
    validator.feed(body)
    validator.finish()
    styles = []
    for index, filename in enumerate(args.style):
        text = expand(read_text(filename), str(filename))
        validate_css(text, str(filename))
        styles.append(f'<link id="av-style-{index}" rel="stylesheet" href="{data_url(text.encode("utf-8"), "text/css;charset=utf-8")}">')
    scripts = []
    features = set(getattr(args, 'feature', []))
    features.update(validator.features)
    if features - {'mermaid'}:
        raise PackagingError('unknown required feature: ' + ', '.join(sorted(features - {'mermaid'})))
    script_paths = list(args.script)
    if 'mermaid' in features:
        vendor = Path(__file__).resolve().parent / 'vendor/mermaid/mermaid.min.js'
        if not vendor.is_file():
            raise PackagingError('Mermaid feature is missing; restore the complete visual library')
        script_paths = [vendor, *(path for path in script_paths if path.resolve() != vendor.resolve())]
    for index, filename in enumerate(script_paths):
        text = expand(read_text(filename), str(filename))
        scripts.append(f'<script id="av-script-{index}" src="{data_url(text.encode("utf-8"), "text/javascript;charset=utf-8")}"></script>')
    head_scripts = []
    if args.script:
        startup = Path(__file__).resolve().parent / 'dist/agentic-startup.js'
        if not startup.is_file():
            raise PackagingError('The startup asset is missing; restore the complete visual library or rebuild its generated assets')
        head_scripts.append(f'<script id="av-startup" src="{data_url(read_text(startup).encode("utf-8"), "text/javascript;charset=utf-8")}"></script>')
    data = []
    for name, filename in data_paths.items():
        if name in validator.ids:
            raise PackagingError(f"--data id {name!r} already exists in the body")
        text = json_content(expand(read_text(filename), str(filename)), str(filename))
        data.append(f'<script type="application/json" id="{html.escape(name, quote=True)}">{text}</script>')
    extra_data_ids = []
    if 'mermaid' in features:
        owner = Path(__file__).resolve().parent / 'vendor/mermaid'
        notices = {str(path.relative_to(owner)): read_text(path) for path in [owner / 'LICENSE', owner / 'NOTICE.md', *sorted((owner / 'licenses').glob('*'))]}
        notice_json = json_content(json.dumps({'name': 'Mermaid', 'version': '12.0.0', 'notices': notices}, ensure_ascii=True), 'Mermaid notices')
        data.append('<script type="application/json" id="av-mermaid-notices">' + notice_json + '</script>')
        extra_data_ids.append('av-mermaid-notices')
    unused = asset_paths.keys() - used_assets
    if unused:
        raise PackagingError(f"unused assets: {', '.join(sorted(unused))}; reference each with an asset token or remove its --asset option")
    title = args.title if args.title is not None else args.output.stem
    recipe = {"kind": "agentic-report-recipe", "version": 1, "lang": args.lang, "title": title, "csp": CSP, "body": body, "styles": [f"av-style-{i}" for i in range(len(styles))], "data": [*data_paths, *extra_data_ids], "scripts": [f"av-script-{i}" for i in range(len(scripts))], "headScripts": ["av-startup"] if head_scripts else []}
    recipe_json = json_content(json.dumps(recipe, ensure_ascii=True, separators=(",", ":")), "report recipe")
    blueprint = '<script type="application/json" id="av-report-recipe">' + recipe_json + '</script>'
    reserved = {"av-report-recipe", "av-review-seed", "av-startup", *extra_data_ids, *recipe["styles"], *recipe["scripts"]}
    if reserved.intersection(validator.ids) or reserved.intersection(data_paths):
        raise PackagingError('av-report-recipe, av-review-seed and generated av-style-/av-script- IDs are reserved for portable export')
    return "\n".join(
        [
            "<!doctype html>",
            f'<html lang="{html.escape(args.lang, quote=True)}">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f'<meta http-equiv="Content-Security-Policy" content="{html.escape(CSP, quote=True)}">',
            f"<title>{html.escape(title)}</title>",
            *head_scripts,
            *styles,
            "</head>",
            "<body>",
            body,
            *data,
            blueprint,
            *scripts,
            "</body>",
            "</html>",
            "",
        ]
    )


def write_output(filename: Path, content: str, replace: bool) -> str:
    if filename.is_symlink() or (filename.exists() and not filename.is_file()):
        raise PackagingError(f"output is not a regular file: {filename}")
    if filename.exists():
        if read_text(filename) == content:
            return "unchanged"
        if not replace:
            raise PackagingError(f"output exists and differs: {filename}; use --replace or choose another --output")
    filename.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".av-assemble-", dir=filename.parent) as scratch:
        temporary = Path(scratch) / "report.html"
        temporary.write_text(content, encoding="utf-8", newline="\n")
        if replace:
            os.replace(temporary, filename)
        else:
            os.link(temporary, filename)
    return "assembled"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--body", required=True, type=Path, help="caller-owned UTF-8 HTML body fragment")
    parser.add_argument("--output", required=True, type=Path, help="standalone HTML output")
    parser.add_argument("--title", help="document title; defaults to output filename stem")
    parser.add_argument("--lang", default="en", help="document language (default: en)")
    parser.add_argument("--style", action="append", default=[], type=Path, help="UTF-8 CSS file; repeat in cascade order")
    parser.add_argument("--script", action="append", default=[], type=Path, help="UTF-8 classic JavaScript file; repeat in execution order")
    parser.add_argument("--data", action="append", default=[], metavar="ID=FILE", help="JSON data embedded under its DOM id")
    parser.add_argument("--asset", action="append", default=[], metavar="NAME=FILE", help="local bytes substituted for {{asset:NAME}} tokens")
    parser.add_argument("--feature", action="append", default=[], choices=["mermaid"], help="embed a feature used by runtime composition; repeat as needed")
    parser.add_argument("--replace", action="store_true", help="authorize replacing a differing existing output")
    args = parser.parse_args()
    try:
        content = assemble(args)
        action = write_output(args.output, content, args.replace)
    except (PackagingError, OSError, UnicodeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        print("hint: correct the named input or output and rerun; dependencies are never downloaded", file=sys.stderr)
        return 1
    print(f"{action} {args.output} ({len(content.encode('utf-8'))} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
