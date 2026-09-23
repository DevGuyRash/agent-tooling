#!/usr/bin/env python3
"""Generate Mermaid references from captured official documentation and renderer metadata.

The vendored Mermaid registry is authoritative for packaged support. Live
upstream documentation is fetched only with the explicit ``--fetch`` maintenance
flag; the split-testing skill, report runtime, normal builds, and offline checks
never require network access.
"""

from __future__ import annotations

import argparse
import html
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urljoin, urlsplit
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins" / "agentic-design-and-evaluation"
VENDOR = PLUGIN / "skills/split-testing/assets/visuals/vendor/mermaid/mermaid.min.js"
INTEGRITY = PLUGIN / "skills/split-testing/assets/visuals/vendor/mermaid/integrity.json"
OUTPUT = PLUGIN / "skills/split-testing/references/mermaid-diagrams.md"

UPSTREAM_REPO = "https://github.com/mermaid-js/mermaid"
UPSTREAM_API = "https://api.github.com/repos/mermaid-js/mermaid"
UPSTREAM_BRANCH = "develop"
DOCS_PATH = "packages/mermaid/src/docs/syntax"
SIDEBAR_PATH = "packages/mermaid/src/docs/.vitepress/config.ts"
LAYOUT_DOCS = "https://mermaid.js.org/config/layouts.html"

COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class CatalogError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def fetch(url: str) -> bytes:
    request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "agent-tooling-mermaid-catalog"})
    try:
        with urlopen(request, timeout=30) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise CatalogError(f"could not fetch {url}: {exc}") from exc


def validate_commit(value: object) -> str:
    if not isinstance(value, str) or not COMMIT_RE.fullmatch(value):
        raise CatalogError("upstream commit must be a 40-character lowercase hexadecimal SHA")
    return value


def validate_docs(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        raise CatalogError("upstream docs index must be a non-empty list")
    for name in value:
        if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.md", name)
                or any(part in {".", ".."} for part in name.split("/"))):
            raise CatalogError("unsafe or unsupported upstream document path")
    if len(value) != len(set(value)):
        raise CatalogError("upstream docs index contains duplicate paths")
    return sorted(value, key=str.casefold)


def validate_sidebar(value: object) -> str:
    if not isinstance(value, str):
        raise CatalogError("upstream sidebar source must be text")
    return value


def load_offline_upstream(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_bytes())
        if not isinstance(payload, dict):
            raise CatalogError("upstream snapshot must be an object")
        commit = validate_commit(payload.get("commit"))
        docs = validate_docs(payload.get("docs"))
        sidebar = validate_sidebar(payload.get("sidebar"))
        pages = validate_pages(payload.get("pages", {}), docs)
        return {"commit": commit, "docs": docs, "sidebar": sidebar, "pages": pages,
                "docs_hash": sha256(canonical_json(docs)),
                "sidebar_hash": sha256(sidebar.encode()), "retrieval": "captured source"}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogError("could not read the upstream snapshot as UTF-8 JSON") from exc


def load_live_upstream() -> dict[str, object]:
    try:
        revision = json.loads(fetch(f"{UPSTREAM_API}/commits/{UPSTREAM_BRANCH}"))
        commit = validate_commit(revision.get("sha") if isinstance(revision, dict) else None)
        docs = []
        pending = [""]
        while pending:
            prefix = pending.pop(0)
            entries = json.loads(fetch(f"{UPSTREAM_API}/contents/{DOCS_PATH}{'/' + prefix if prefix else ''}?ref={commit}"))
            if not isinstance(entries, list):
                raise CatalogError("upstream syntax-directory response changed shape")
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
                    raise CatalogError("upstream directory entry changed shape")
                name = "/".join(filter(None, [prefix, entry["name"]]))
                if entry.get("type") == "dir":
                    if not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", name) or ".." in name.split("/"):
                        raise CatalogError("unsafe upstream directory")
                    pending.append(name)
                elif entry.get("type") == "file" and name.endswith(".md"):
                    docs.append(name)
        docs = validate_docs(docs)
        sidebar = fetch(f"https://raw.githubusercontent.com/mermaid-js/mermaid/{commit}/{SIDEBAR_PATH}").decode("utf-8")
        def capture(name):
            return name, fetch(f"https://raw.githubusercontent.com/mermaid-js/mermaid/{commit}/{DOCS_PATH}/{name}").decode("utf-8")
        with ThreadPoolExecutor(max_workers=6) as pool:
            pages = dict(pool.map(capture, docs))
        validate_pages(pages, docs)
        return {"commit": commit, "docs": docs, "sidebar": sidebar, "pages": pages,
                "docs_hash": sha256(canonical_json(docs)), "sidebar_hash": sha256(sidebar.encode()),
                "retrieval": "captured source"}
    except (UnicodeError, json.JSONDecodeError, TypeError) as exc:
        raise CatalogError("upstream response is incomplete or changed format") from exc


def upstream_fixture_payload(upstream: dict[str, object]) -> dict[str, object]:
    docs = validate_docs(upstream.get("docs"))
    return {"commit": validate_commit(upstream.get("commit")), "docs": docs,
            "sidebar": validate_sidebar(upstream.get("sidebar")),
            "pages": validate_pages(upstream.get("pages", {}), docs)}


def read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogError(f"could not read JSON {path}: {exc}") from exc


def fixture_starter(source: str, family: str) -> str | None:
    """Return the authored diagram starter after optional Mermaid preamble."""
    lines = source.splitlines()
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1
    if family != "---" and index < len(lines) and lines[index].strip() == "---":
        index += 1
        while index < len(lines) and lines[index].strip() != "---":
            index += 1
        if index < len(lines):
            index += 1
    while index < len(lines):
        stripped = lines[index].strip()
        index += 1
        if not stripped or stripped.startswith("%%"):
            continue
        return stripped.split()[0]
    return None


REGISTRY_NODE = r"""
const fs=require('node:fs'),vm=require('node:vm');
const vendor=process.argv[1];
const source=fs.readFileSync(vendor,'utf8');
const context=vm.createContext({console:{log(){},warn(){},error(){}},structuredClone,setTimeout,clearTimeout});
vm.runInContext(source,context,{timeout:10000});
context.mermaid.initialize({startOnLoad:false,securityLevel:'strict'});
process.stdout.write(JSON.stringify(context.mermaid.getRegisteredDiagramsMetadata().map(item=>item.id)));
"""

DETECT_NODE = r"""
const fs=require('node:fs'),vm=require('node:vm');
const vendor=process.argv[1],starters=JSON.parse(process.argv[2]);
const source=fs.readFileSync(vendor,'utf8');
const context=vm.createContext({console:{log(){},warn(){},error(){}},structuredClone,setTimeout,clearTimeout});
vm.runInContext(source,context,{timeout:10000});
context.mermaid.initialize({startOnLoad:false,securityLevel:'strict'});
const result={};
for(const starter of starters){try{result[starter]=context.mermaid.detectType(starter+'\n');}catch{}}
process.stdout.write(JSON.stringify(result));
"""


def run_node(script: str, *arguments: str) -> object:
    node = shutil.which("node")
    if not node:
        raise CatalogError("Node.js is required to inspect the bundled Mermaid registry")
    process = subprocess.run(
        [node, "-e", script, *arguments],
        cwd=REPO,
        text=True,
        capture_output=True,
        timeout=30,
    )
    if process.returncode:
        detail = (process.stderr or process.stdout).strip()
        raise CatalogError(f"bundled Mermaid inspection failed: {detail or 'Node exited non-zero'}")
    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise CatalogError("bundled Mermaid inspection returned invalid JSON") from exc


def bundled_registry() -> list[str]:
    value = run_node(REGISTRY_NODE, str(VENDOR))
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise CatalogError("bundled Mermaid registry did not return a list of family ids")
    if len(value) != len(set(value)):
        raise CatalogError("bundled Mermaid registry contains duplicate family ids")
    return value


def markdown_code(value: str) -> str:
    fence = "`"
    while fence in value:
        fence += "`"
    return f"{fence}{value}{fence}"


EXAMPLE_RE = re.compile(r"(?ms)^[ \t]*(" + chr(96) + r"{3,}|~{3,})mermaid(?:-example)?[^\n]*\n(.*?)^[ \t]*\1[ \t]*$")


def validate_pages(pages, docs):
    if not isinstance(pages, dict) or any(name not in docs or not isinstance(body, str) for name, body in pages.items()):
        raise CatalogError("upstream page content is invalid")
    if set(pages) != set(docs):
        raise CatalogError("upstream page capture is incomplete")
    return pages


def page_meta(source):
    match = re.match(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", source, re.S)
    if not match:
        return {}, source
    result = {}
    lines = match.group(1).splitlines()
    for index, line in enumerate(lines):
        field = re.match(r"^(title|description|permalink|url):[ \t]*(.*)$", line)
        if not field:
            continue
        key, value = field.groups()
        if value in ("|", ">", "|-", ">-", "|+", ">+"):
            parts = []
            for continuation in lines[index + 1:]:
                if continuation and not continuation[0].isspace():
                    break
                parts.append(continuation.strip())
            value = " ".join(parts).strip()
        elif len(value) > 1 and value[0] == value[-1] and value[0] in "'\"":
            if value[0] == '"':
                try:
                    value = json.loads(value)
                except ValueError:
                    continue
            else:
                value = value[1:-1].replace("''", "'")
        if value:
            result[key] = value
    return result, source[match.end():]


def page_title(source, name):
    meta, body = page_meta(source)
    heading = re.search(r"(?m)^#\s+(.+?)\s*$", body)
    return meta.get("title") or (heading.group(1) if heading else name.removesuffix(".md"))


def page_introduction(source):
    meta, body = page_meta(source)
    if meta.get("description"):
        return meta["description"], []
    body = re.sub(r"(?s)<!--.*?-->", "", body)
    inside = None
    notices = []
    for paragraph in re.split(r"\n[ \t]*\n", body):
        kept, structural = [], False
        for line in paragraph.splitlines():
            value = line.strip()
            fence = re.match(r"^(" + chr(96) + r"{3,}|~{3,})", value)
            if fence:
                inside = fence.group(1)[0] if inside is None else None
                structural = True
            elif inside:
                structural = True
            elif not value:
                continue
            elif value.startswith(("#", ":::")) or re.match(r"^(?:<[/!]?[A-Za-z]|\|)", value):
                structural = True
            else:
                kept.append(re.sub(r"^>\s?", "", value))
        if structural or not kept:
            continue
        value = " ".join(kept).strip()
        if value.startswith("[!") or re.match(r"^(?:\*\*)?(?:Warning|Note|Tip|Caution|Danger)(?:\*\*)?(?::|\s*$)", value, re.I):
            continue
        if re.match(r"^(?:[-*+] |\d+[.)] )", value):
            continue
        if re.search(r"\b(?:experimental (?:diagram|feature|syntax)|(?:is|are) (?:an? )?(?:experimental|deprecated))\b", value, re.I):
            notices.append(value)
            continue
        return value, notices
    return None, notices


def page_description(source):
    return page_introduction(source)[0]


def page_link(name, source, sidebar, commit):
    meta, _body = page_meta(source)
    explicit = meta.get("permalink") or meta.get("url")
    if explicit:
        url = urljoin("https://mermaid.js.org", explicit)
        if urlsplit(url).scheme == "https" and urlsplit(url).netloc == "mermaid.js.org":
            return quote(url, safe=":/?#[]@!$&\'*+,;=%~")
    slug = name.removesuffix(".md").casefold()
    routes = [route for route in re.findall(r"""link\s*:\s*['"](/syntax/[^'"\s?#]+)['"]""", sidebar)
              if route.removeprefix("/syntax/").removesuffix(".html").casefold() == slug]
    if len(set(routes)) == 1:
        return quote(urljoin("https://mermaid.js.org", routes[0]), safe=":/?#[]@!$&\'*+,;=%~")
    return f"{UPSTREAM_REPO}/blob/{commit}/{DOCS_PATH}/{name}"


def md_cell(value):
    return html.escape(re.sub(r"\s+", " ", str(value)).strip(), quote=False).replace("|", r"\|")


def md_label(value):
    return md_cell(value).replace("[", r"\[").replace("]", r"\]")


def build_markdown(upstream: dict[str, object], profile="bundled", hints=None) -> str:
    commit = validate_commit(upstream.get("commit"))
    docs = validate_docs(upstream.get("docs"))
    sidebar = validate_sidebar(upstream.get("sidebar"))
    pages = validate_pages(upstream.get("pages", {}), docs)
    examples = {name: [fixture_starter(match.group(2), "") for match in EXAMPLE_RE.finditer(pages.get(name, ""))]
                for name in docs}
    examples = {name: list(dict.fromkeys(value for value in values if value)) for name, values in examples.items()}
    registry, detected, info = [], {}, {}
    if profile == "bundled":
        info = read_json(INTEGRITY)
        if (not isinstance(info, dict) or not isinstance(info.get("version"), str)
                or sha256(VENDOR.read_bytes()) != info.get("artifactSha256")):
            raise CatalogError("renderer bytes do not match their integrity metadata")
        registry = bundled_registry()
        candidates = sorted({value for values in examples.values() for value in values})
        detected = run_node(DETECT_NODE, str(VENDOR), json.dumps(candidates))
        if not isinstance(detected, dict):
            raise CatalogError("renderer detector response changed shape")
    elif profile != "upstream":
        raise CatalogError("profile must be bundled or upstream")
    lines = ["<!-- Generated by the repository Mermaid catalog task. -->",
             "# Mermaid diagram reference", "",
             f"Documentation source: [Mermaid {commit[:12]}]({UPSTREAM_REPO}/tree/{commit}/{DOCS_PATH}).",
             "Descriptions are excerpts from official documentation. Follow the linked source for syntax and qualifications.", ""]
    if profile == "upstream":
        lines += ["## Documented diagram topics", "",
                  "This reference covers the captured upstream syntax documentation. Select syntax supported by the receiving renderer.", "",
                  "| Topic | Description | Documented starters | Documentation |",
                  "| --- | --- | --- | --- |"]
        for name in docs:
            body = pages.get(name, "")
            lines.append("| " + " | ".join([
                md_cell(page_title(body, name)), md_cell(page_description(body) or "Description unavailable in the captured source."),
                ", ".join(markdown_code(md_cell(value)) for value in examples[name]) or "—",
                f"[Official source]({page_link(name, body, sidebar, commit)})"]) + " |")
    else:
        lines += [f"Packaged renderer: **Mermaid {md_cell(info['version'])}**, artifact SHA-256 {markdown_code(info['artifactSha256'])}.",
                  f"The renderer registers {len(registry)} entries. Starter observations come from documented examples inspected against this artifact.",
                  "", "## Registered renderer entries", "",
                  "| Registered entry | Description | Documented starters detected here | Documentation |",
                  "| --- | --- | --- | --- |"]
        used = set()
        for family in sorted(registry, key=str.casefold):
            candidates = [name for name in docs if family in {detected.get(value) for value in examples[name]}]
            primary = [name for name in candidates if examples[name] and detected.get(examples[name][0]) == family]
            if len(primary) == 1:
                candidates = primary
            if hints and hints.get(family) in docs:
                candidates = [hints[family]]
            starts = sorted({value for name in candidates for value in examples[name] if detected.get(value) == family}, key=str.casefold)
            description = (page_description(pages.get(candidates[0], "")) or "Description unavailable in the captured source.") if len(candidates) == 1 else (
                "Several documentation topics contain this entry; inspect the linked sources." if candidates else "No matching authoring description in the captured sources.")
            links = [f"[{md_label(page_title(pages.get(name, ''), name))}]({page_link(name, pages.get(name, ''), sidebar, commit)})" for name in candidates]
            used.update(candidates)
            lines.append("| " + " | ".join([markdown_code(md_cell(family)), md_cell(description),
                ", ".join(markdown_code(md_cell(value)) for value in starts) or "—", "; ".join(links) or "—"]) + " |")
        remaining = [name for name in docs if name not in used]
        if remaining:
            lines += ["", "## Additional upstream documentation", "", "| Topic | Description | Documentation |", "| --- | --- | --- |"]
            for name in remaining:
                body = pages.get(name, "")
                lines.append("| " + " | ".join([md_cell(page_title(body, name)),
                    md_cell(page_description(body) or "Description unavailable in the captured source."),
                    f"[Official source]({page_link(name, body, sidebar, commit)})"]) + " |")
    qualifications = [(name, page_introduction(pages[name])[1]) for name in docs]
    qualifications = [(name, notes) for name, notes in qualifications if notes]
    if qualifications:
        lines += ["", "## Source qualifications", ""]
        for name, notes in qualifications:
            lines.append(f"- [{md_label(page_title(pages[name], name))}]({page_link(name, pages[name], sidebar, commit)}): " + " ".join(md_cell(note) for note in notes))
    lines += ["", "## Source identity", "",
              f"Captured documentation SHA-256: {markdown_code(sha256(canonical_json(upstream_fixture_payload(upstream))))}.",
              f"Layout configuration: [official documentation]({LAYOUT_DOCS}).", ""]
    return "\n".join(lines)


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temp_path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def write_new_atomic(path: Path, data: bytes) -> None:
    """Atomically create a new evidence file and never replace an existing path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.exists():
        raise CatalogError(f"upstream snapshot destination already exists: {path}; choose a new --save-upstream path")
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temp_path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp_path, path)
        except FileExistsError as exc:
            raise CatalogError(f"upstream snapshot destination already exists: {path}; choose a new --save-upstream path") from exc
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def validate_paths(args: argparse.Namespace) -> tuple[Path, Path | None, Path | None]:
    output = args.output.resolve()
    fixture = args.upstream_fixture.resolve() if args.upstream_fixture else None
    save = args.save_upstream.resolve() if args.save_upstream else None
    protected_sources = {
        Path(__file__).resolve(): "updater source",
        VENDOR.resolve(): "vendored Mermaid artifact",
        INTEGRITY.resolve(): "Mermaid integrity metadata",
    }
    if output in protected_sources:
        raise CatalogError(f"output collides with {protected_sources[output]}: {output}")
    if fixture is not None and output == fixture:
        raise CatalogError(f"output collides with upstream fixture input: {output}")
    if save is not None:
        if save == output:
            raise CatalogError(f"--save-upstream collides with generated reference output: {save}")
        if save in protected_sources:
            raise CatalogError(f"--save-upstream collides with {protected_sources[save]}: {save}")
        if save.is_symlink() or save.exists():
            raise CatalogError(f"upstream snapshot destination already exists: {save}; choose a new --save-upstream path")
    return output, fixture, save


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write", action="store_true")
    action.add_argument("--check", action="store_true")
    action.add_argument("--snapshot-only", action="store_true")
    upstream = parser.add_mutually_exclusive_group(required=True)
    upstream.add_argument("--fetch", action="store_true")
    upstream.add_argument("--upstream-fixture", type=Path)
    parser.add_argument("--save-upstream", type=Path)
    parser.add_argument("--profile", choices=("bundled", "upstream"), default="bundled")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--hints", type=Path, help="optional JSON map of registry IDs to captured document paths")
    args = parser.parse_args(argv)
    if args.save_upstream and not args.fetch:
        parser.error("--save-upstream requires --fetch")
    if args.snapshot_only and not (args.fetch and args.save_upstream):
        parser.error("--snapshot-only requires --fetch and --save-upstream")
    if args.output is None:
        args.output = OUTPUT if args.profile == "bundled" else REPO / "plugins/visualization/skills/mermaid/references/mermaid-diagrams.md"
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        output, fixture, save = validate_paths(args)
        upstream = load_live_upstream() if args.fetch else load_offline_upstream(fixture)
        generated = None
        if not args.snapshot_only:
            hints = read_json(args.hints) if args.hints else None
            if hints is not None and (not isinstance(hints, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in hints.items())):
                raise CatalogError("hints must map registry IDs to captured document paths")
            generated = build_markdown(upstream, args.profile, hints)
        if save is not None:
            write_new_atomic(save, canonical_json(upstream_fixture_payload(upstream)))
        if args.snapshot_only:
            print(f"captured {len(upstream['docs'])} official source pages: {save}")
        elif args.check:
            if not output.is_file() or output.read_text(encoding="utf-8") != generated:
                print(f"stale: {output}", file=sys.stderr)
                return 1
            print(f"current: {output}")
        else:
            write_atomic(output, generated)
            print(f"wrote: {output}")
        return 0
    except (CatalogError, OSError, UnicodeError, ValueError, subprocess.TimeoutExpired) as exc:
        message = "renderer inspection timed out" if isinstance(exc, subprocess.TimeoutExpired) else str(exc)
        print(f"error: {message}\nhint: inspect the source/profile; the maintained reference was not replaced", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
