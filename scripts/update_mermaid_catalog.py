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
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPException
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins" / "agentic-design-and-evaluation"
VENDOR = PLUGIN / "skills/split-testing/assets/visuals/vendor/mermaid/mermaid.min.js"
INTEGRITY = PLUGIN / "skills/split-testing/assets/visuals/vendor/mermaid/integrity.json"
OUTPUT = PLUGIN / "skills/split-testing/references/mermaid-diagrams.md"

UPSTREAM_REPO = "https://github.com/mermaid-js/mermaid"
UPSTREAM_API = "https://api.github.com/repos/mermaid-js/mermaid"
# These paths support older captured snapshots. Live discovery uses repository
# metadata and its complete tree; neither a branch nor a family list is pinned.
DOCS_PATH = "packages/mermaid/src/docs/syntax"
LAYOUT_DOCS = "https://mermaid.js.org/config/layouts.html"
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
FETCH_ATTEMPTS = 3

COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class CatalogError(RuntimeError):
    pass


class MissingResource(CatalogError):
    """A published page may legitimately not exist yet."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def fetch(url: str) -> bytes:
    accept = "application/vnd.github+json" if urlsplit(url).netloc == "api.github.com" else "*/*"
    request = Request(url, headers={"Accept": accept, "User-Agent": "agent-tooling-mermaid-catalog"})
    for attempt in range(FETCH_ATTEMPTS):
        try:
            with urlopen(request, timeout=30) as response:
                result = response.read(MAX_RESPONSE_BYTES + 1)
                if len(result) > MAX_RESPONSE_BYTES:
                    raise CatalogError(f"upstream response exceeds the size limit: {url}")
                return result
        except HTTPError as exc:
            if exc.code in {404, 410}:
                raise MissingResource(f"upstream page unavailable (HTTP {exc.code}): {url}") from exc
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            retryable = exc.code in {408, 429, 500, 502, 503, 504} or (exc.code == 403 and retry_after is not None)
            delay = retry_delay(retry_after, attempt)
            if not retryable or attempt == FETCH_ATTEMPTS - 1 or delay is None:
                raise CatalogError(f"upstream request failed (HTTP {exc.code}): {url}") from exc
        except (URLError, TimeoutError, OSError, HTTPException) as exc:
            if attempt == FETCH_ATTEMPTS - 1:
                raise CatalogError(f"upstream request failed after {FETCH_ATTEMPTS} attempts: {url}") from exc
            delay = retry_delay(None, attempt)
        time.sleep(delay)
    raise CatalogError(f"upstream request did not complete: {url}")


def retry_delay(value: str | None, attempt: int) -> float | None:
    delay = float(2 ** attempt)
    if value:
        try:
            delay = max(0, float(value))
        except ValueError:
            try:
                delay = max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
            except (ValueError, TypeError, OverflowError):
                pass
    # Do not busy-retry a long server-directed backoff or block a hook indefinitely.
    return delay if delay <= 10 else None


def source_path(value: object) -> str:
    if (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", value)
            or any(part in {".", ".."} for part in value.split("/"))):
        raise CatalogError("unsafe or unsupported upstream source path")
    return value


def web_url(value: object, base: str = "") -> str | None:
    if not isinstance(value, str) or re.search(r"[\s\x00-\x1f\x7f]", value):
        return None
    parsed = urlsplit(urljoin(base, value))
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return None
    return quote(urlunsplit(parsed), safe=":/?#@!$&'*+,;=%~")


class PublishedPage(HTMLParser):
    def __init__(self, body: str, url: str):
        super().__init__(convert_charrefs=True)
        self.url, self.canonical, self.links = url, None, []
        self.heading, self._heading_depth = "", 0
        self.feed(body)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "a" and (link := web_url(attrs.get("href"), self.url)):
            self.links.append(link)
        if tag == "link" and "canonical" in attrs.get("rel", "").split():
            self.canonical = web_url(attrs.get("href"), self.url)
        if tag == "h1":
            self._heading_depth += 1

    def handle_endtag(self, tag):
        if tag == "h1":
            self._heading_depth = max(0, self._heading_depth - 1)

    def handle_data(self, value):
        if self._heading_depth:
            self.heading += value


def document_key(value: str) -> str:
    value = unquote(value).rstrip("/")
    value = re.sub(r"\.(?:mdx?|html)$", "", value, flags=re.I)
    return value.removesuffix("/index").casefold()


def published_navigation(homepage: str) -> tuple[str, str, list[str]]:
    """Follow the official repository's home/navigation, including docs migrations."""
    pending, seen = [homepage], set()
    origin = urlsplit(homepage).netloc
    while pending and len(seen) < 8:
        url = pending.pop(0)
        if url in seen:
            continue
        seen.add(url)
        body = fetch(url).decode("utf-8")
        page = PublishedPage(body, url)
        routes = [link for link in page.links if "/syntax/" in urlsplit(link).path
                  and urlsplit(link).netloc == origin]
        if routes:
            return url, body, list(dict.fromkeys(routes))
        pending.extend(link for link in page.links
                       if urlsplit(link).netloc == origin and link.startswith(homepage)
                       and not urlsplit(link).fragment and link not in seen and link not in pending)
    raise CatalogError("published documentation navigation has no discoverable syntax routes")


def validate_commit(value: object) -> str:
    if not isinstance(value, str) or not COMMIT_RE.fullmatch(value):
        raise CatalogError("upstream commit must be a 40-character lowercase hexadecimal SHA")
    return value


def validate_docs(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        raise CatalogError("upstream docs index must be a non-empty list")
    for name in value:
        if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.mdx?", name)
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
        return upstream_fixture_payload(payload)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogError("could not read the upstream snapshot as UTF-8 JSON") from exc


def load_live_upstream() -> dict[str, object]:
    try:
        repository = json.loads(fetch(UPSTREAM_API))
        branch = repository.get("default_branch") if isinstance(repository, dict) else None
        homepage = web_url(repository.get("homepage")) if isinstance(repository, dict) else None
        if not isinstance(branch, str) or not branch.strip() or not homepage:
            raise CatalogError("repository metadata lacks its default branch or official documentation home")
        homepage = homepage.rstrip("/") + "/"
        revision = json.loads(fetch(f"{UPSTREAM_API}/commits/{quote(branch, safe='')}"))
        commit = validate_commit(revision.get("sha") if isinstance(revision, dict) else None)
        tree = json.loads(fetch(f"{UPSTREAM_API}/git/trees/{commit}?recursive=1"))
        if not isinstance(tree, dict) or tree.get("truncated") is not False or not isinstance(tree.get("tree"), list):
            raise CatalogError("upstream repository tree is incomplete or changed shape")
        paths = []
        for entry in tree["tree"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                raise CatalogError("upstream repository tree entry changed shape")
            if entry.get("type") == "blob":
                paths.append(entry["path"])
        roots = {match.group(1) for path in paths
                 if (match := re.fullmatch(r"((?:.*/)?(?:docs|doc)/syntax)/.+\.mdx?", path))}
        configured_roots = {root for root in roots if any(
            re.fullmatch(re.escape(root.rsplit("/", 1)[0]) + r"/\.vitepress/config\.[cm]?[jt]s", path)
            for path in paths)}
        if configured_roots:
            roots = configured_roots
        if len(roots) != 1:
            raise CatalogError("cannot identify one authoritative syntax-documentation directory in the upstream tree")
        docs_path = source_path(roots.pop())
        docs = validate_docs([path[len(docs_path) + 1:] for path in paths
                              if path.startswith(docs_path + "/") and re.search(r"\.mdx?$", path)])
        nav_paths = sorted(path for path in paths if path.startswith(docs_path.rsplit("/", 1)[0] + "/.vitepress/")
                           and re.fullmatch(r"(?:config|sidebar|nav)(?:[.-][\w-]+)?\.[cm]?[jt]s", Path(path).name))
        raw_root = f"https://raw.githubusercontent.com/mermaid-js/mermaid/{commit}/"
        navigation = {source_path(path): fetch(raw_root + path).decode("utf-8") for path in nav_paths}
        sidebar = "\n".join(navigation.values())
        def capture(name):
            return name, fetch(f"{raw_root}{docs_path}/{name}").decode("utf-8")
        with ThreadPoolExecutor(max_workers=6) as pool:
            pages = dict(pool.map(capture, docs))
        validate_pages(pages, docs)
        nav_url, nav_html, routes = published_navigation(homepage)
        published = discover_published_links(docs, pages, homepage, routes)
        return upstream_fixture_payload({"commit": commit, "docs": docs, "sidebar": sidebar, "pages": pages,
                "source": {"default_branch": branch, "docs_path": docs_path, "homepage": homepage},
                "navigation_sources": navigation,
                "published_navigation": {"url": nav_url, "html": nav_html}, "published_links": published})
    except (UnicodeError, json.JSONDecodeError, TypeError) as exc:
        raise CatalogError("upstream response is incomplete or changed format") from exc


def upstream_fixture_payload(upstream: dict[str, object]) -> dict[str, object]:
    docs = validate_docs(upstream.get("docs"))
    result = {"commit": validate_commit(upstream.get("commit")), "docs": docs,
            "sidebar": validate_sidebar(upstream.get("sidebar")),
            "pages": validate_pages(upstream.get("pages", {}), docs)}
    if "source" in upstream:
        source = upstream["source"]
        if not isinstance(source, dict) or not isinstance(source.get("default_branch"), str) or not source["default_branch"]:
            raise CatalogError("captured repository metadata is invalid")
        homepage = web_url(source.get("homepage"))
        if not homepage:
            raise CatalogError("captured documentation homepage is invalid")
        result["source"] = {"default_branch": source["default_branch"],
                            "docs_path": source_path(source.get("docs_path")), "homepage": homepage}
        navigation = upstream.get("navigation_sources")
        if not isinstance(navigation, dict) or any(not isinstance(body, str) for body in navigation.values()):
            raise CatalogError("captured source navigation is invalid")
        for name in navigation:
            source_path(name)
        result["navigation_sources"] = navigation
        published = upstream.get("published_navigation")
        if not isinstance(published, dict) or not web_url(published.get("url")) or not isinstance(published.get("html"), str):
            raise CatalogError("captured published navigation is invalid")
        links = upstream.get("published_links")
        if not isinstance(links, dict) or set(links) != set(docs):
            raise CatalogError("captured published-link coverage is incomplete")
        for link in links.values():
            if link is not None and (not web_url(link) or urlsplit(link).netloc != urlsplit(homepage).netloc):
                raise CatalogError("captured published link is outside the official documentation origin")
        result.update(published_navigation=published, published_links=links)
    return result


def discover_published_links(docs, pages, homepage, routes):
    origin = urlsplit(homepage).netloc
    by_key = {}
    templates = set()
    for route in routes:
        path = urlsplit(route).path
        prefix, suffix = path.split("/syntax/", 1)
        by_key.setdefault(document_key(suffix), set()).add(route.split("#", 1)[0].split("?", 1)[0])
        # Learn the publishing convention from live navigation, rather than
        # maintain a family-to-URL table. Every resulting candidate is fetched.
        templates.add((prefix + "/syntax/", ".html" if suffix.endswith(".html") else "/" if suffix.endswith("/") else ""))
    def discover(name):
        meta, _body = page_meta(pages[name])
        explicit = web_url(meta.get("permalink") or meta.get("url"), homepage)
        candidates = [explicit] if explicit and urlsplit(explicit).netloc == origin else []
        candidates.extend(sorted(by_key.get(document_key(name), set())))
        if len(templates) == 1:
            prefix, suffix = next(iter(templates))
            candidates.append(urljoin(homepage, prefix + re.sub(r"\.mdx?$", "", name) + suffix))
        for url in dict.fromkeys(candidates):
            try:
                page = PublishedPage(fetch(url).decode("utf-8"), url)
            except MissingResource:
                continue
            if not page.heading.strip() or re.search(r"\b(?:404|page not found)\b", page.heading, re.I):
                continue
            canonical = page.canonical or url
            if urlsplit(canonical).netloc != origin:
                continue
            if page.canonical and document_key(urlsplit(canonical).path) != document_key(urlsplit(url).path):
                continue  # a soft redirect to a generic landing page is not this document
            return name, canonical
        return name, None
    with ThreadPoolExecutor(max_workers=6) as pool:
        return dict(pool.map(discover, docs))


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
        detail = next((line for line in (process.stderr or "").splitlines()
                       if re.match(r"^[A-Za-z]*Error:", line)), f"Node exited with status {process.returncode}")
        raise CatalogError(f"bundled Mermaid inspection failed: {detail[:240]}")
    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise CatalogError("bundled Mermaid inspection returned invalid JSON") from exc


def bundled_registry() -> list[str]:
    value = run_node(REGISTRY_NODE, str(VENDOR))
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise CatalogError("bundled Mermaid registry did not return a list of family ids")
    if len(value) != len(set(value)):
        raise CatalogError("bundled Mermaid registry contains duplicate family ids")
    return value


def markdown_code(value: str) -> str:
    fence = "`"
    while fence in value:
        fence += "`"
    return f"{fence}{value}{fence}"


def documented_examples(source):
    fence, mermaid, lines = None, False, []
    for line in source.splitlines():
        match = re.match(r"^[ \t]*(`{3,}|~{3,})(.*)$", line)
        if fence is None:
            if match:
                fence = match[1]
                mermaid = re.match(r"^\s*mermaid(?:-example)?(?:\s|\{|$)", match[2]) is not None
                lines = []
        elif match and match[1][0] == fence[0] and len(match[1]) >= len(fence) and not match[2].strip():
            if mermaid:
                yield "\n".join(lines)
            fence = None
        else:
            lines.append(line)


def validate_pages(pages, docs):
    if not isinstance(pages, dict) or any(name not in docs or not isinstance(body, str) for name, body in pages.items()):
        raise CatalogError("upstream page content is invalid")
    if set(pages) != set(docs):
        raise CatalogError("upstream page capture is incomplete")
    if any(not body.strip() for body in pages.values()):
        raise CatalogError("upstream page capture contains an empty document")
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
    return meta.get("title") or (heading.group(1) if heading else re.sub(r"\.mdx?$", "", name))


def page_introduction(source):
    meta, body = page_meta(source)
    body = re.sub(r"(?s)<!--.*?-->", "", body)
    description, notices, paragraphs = meta.get("description"), [], []
    group, kind, fence, container = [], None, None, False
    def flush():
        nonlocal group
        if group:
            paragraphs.append((kind, " ".join(group).strip()))
            group = []
    for line in body.splitlines():
        value = line.strip()
        fence_match = re.match(r"^(`{3,}|~{3,})(.*)$", value)
        if fence:
            if fence_match and fence_match[1][0] == fence[0] and len(fence_match[1]) >= len(fence) and not fence_match[2].strip():
                fence = None
            continue
        if fence_match:
            flush(); fence = fence_match[1]; continue
        if value.startswith(":::"):
            flush(); container = not container; kind = "notice" if container else None; continue
        if re.match(r"^#{2,}\s", value) and (description or any(p[1] for p in paragraphs)):
            flush(); break
        if not value or re.fullmatch(r">\s*", value) or value.startswith("#"):
            flush(); continue
        if re.match(r"^(?:<[/!]?[A-Za-z]|!\[|\||[-*+] |\d+[.)] )", value):
            flush(); continue
        line_kind = "notice" if container else "quote" if value.startswith(">") else "prose"
        if line_kind != kind:
            flush(); kind = line_kind
        group.append(re.sub(r"^>\s?", "", value))
    flush()
    for kind, value in paragraphs:
        warning = re.match(r"^(?:\[!(?:WARNING|NOTE|TIP|CAUTION|DANGER)\]|\*\*(?:Warning|Note|Tip|Caution|Danger)\*\*|(?:Warning|Note|Tip|Caution|Danger):)(?:\s|$)", value, re.I)
        qualified = re.search(r"\b(?:experimental (?:diagram|feature|syntax)|(?:is|are) (?:an? )?(?:experimental|deprecated)|syntax (?:may|can) (?:still )?change)\b", value, re.I)
        if kind == "notice" or warning or qualified:
            notices.append(value)
        elif description is None:
            description = value
    return description, notices


def page_description(source):
    return page_introduction(source)[0]


def description_excerpt(source):
    """Use a complete upstream sentence; full meaning and caveats remain linked."""
    value = page_description(source)
    if not value:
        return "Description unavailable in the captured source."
    value = re.sub(r"\[([^\]]+)\]\([^\n]*?\)", r"\1", value)
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z\"“])", value)
    excerpt = sentences[0]
    if excerpt.startswith('"') and excerpt.count('"') == 1:
        excerpt += '"'
    elif excerpt.startswith('“') and '”' not in excerpt:
        excerpt += '”'
    return excerpt


def page_link(name, source, sidebar, commit, upstream=None):
    if upstream and "published_links" in upstream:
        return upstream["published_links"].get(name) or source_link(name, upstream, latest=True)
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


def source_link(name, upstream, *, latest=False):
    revision = "HEAD" if latest else validate_commit(upstream.get("commit"))
    path = upstream.get("source", {}).get("docs_path", DOCS_PATH)
    return f"{UPSTREAM_REPO}/blob/{revision}/{path}/{quote(name, safe='/')}"


def documentation_links(name, upstream):
    published = page_link(name, upstream["pages"][name], upstream["sidebar"], upstream["commit"], upstream)
    latest = source_link(name, upstream, latest=True)
    main_label = "Docs" if published != latest else "Latest source"
    return f"[{main_label}]({published}) · [Captured source]({source_link(name, upstream)})"


def source_notice(value, name, upstream):
    def link(match):
        label, destination = match.groups()
        url = web_url(destination, source_link(name, upstream))
        return f"[{label}]({url})" if url else label
    return re.sub(r"\[([^\]]+)\]\(([^\s)]+)\)", link, value)


def md_cell(value):
    return html.escape(re.sub(r"\s+", " ", str(value)).strip(), quote=False).replace("\\", "\\\\").replace("|", r"\|")


def md_label(value):
    return md_cell(value).replace("[", r"\[").replace("]", r"\]")


def build_markdown(upstream: dict[str, object], profile="bundled", hints=None) -> str:
    commit = validate_commit(upstream.get("commit"))
    docs = validate_docs(upstream.get("docs"))
    sidebar = validate_sidebar(upstream.get("sidebar"))
    pages = validate_pages(upstream.get("pages", {}), docs)
    examples = {name: [fixture_starter(example, "") for example in documented_examples(pages[name])]
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
        if (not isinstance(detected, dict) or any(key not in candidates or value not in registry
                                                for key, value in detected.items())):
            raise CatalogError("renderer detector response changed shape")
    elif profile != "upstream":
        raise CatalogError("profile must be bundled or upstream")
    docs_path = upstream.get("source", {}).get("docs_path", DOCS_PATH)
    lines = ["<!-- Generated by the repository Mermaid catalog task. -->",
             "# Mermaid diagram reference", "",
             f"Documentation source: [captured Mermaid revision {commit[:12]}]({UPSTREAM_REPO}/tree/{commit}/{docs_path}) · [latest source]({UPSTREAM_REPO}/tree/HEAD/{docs_path}).",
             "Descriptions are short excerpts from official documentation. Docs links follow published pages; captured-source links preserve the exact grounds of this reference.", ""]
    if profile == "upstream":
        lines += ["## Documented diagram topics", "",
                  "This reference covers the captured upstream syntax documentation. Select syntax supported by the receiving renderer.", "",
                  "| Topic | Description | Documented starters | Documentation |",
                  "| --- | --- | --- | --- |"]
        for name in docs:
            body = pages.get(name, "")
            lines.append("| " + " | ".join([
                md_cell(page_title(body, name)), md_cell(description_excerpt(body)),
                ", ".join(markdown_code(md_cell(value)) for value in examples[name]) or "—",
                documentation_links(name, upstream)]) + " |")
    else:
        lines += [f"Packaged renderer: **Mermaid {md_cell(info['version'])}**, artifact SHA-256 {markdown_code(info['artifactSha256'])}.",
                  f"The renderer registers {len(registry)} entries. Starter observations come from documented examples inspected against this artifact.",
                  "", "## Registered renderer entries", "",
                  "| Registered entry | Description | Documented starters detected here | Documentation |",
                  "| --- | --- | --- | --- |"]
        used, unmatched = set(), []
        for family in sorted(registry, key=str.casefold):
            candidates = [name for name in docs if family in {detected.get(value) for value in examples[name]}]
            primary = [name for name in candidates if examples[name] and detected.get(examples[name][0]) == family]
            if len(primary) == 1:
                candidates = primary
            if hints and hints.get(family) in docs:
                candidates = [hints[family]]
            starts = sorted({value for name in candidates for value in examples[name] if detected.get(value) == family}, key=str.casefold)
            description = description_excerpt(pages.get(candidates[0], "")) if len(candidates) == 1 else (
                "Several documentation topics contain this entry; inspect the linked sources." if candidates else "No matching authoring description in the captured sources.")
            links = [((md_cell(page_title(pages[name], name)) + ": ") if len(candidates) > 1 else "") + documentation_links(name, upstream) for name in candidates]
            used.update(candidates)
            row = "| " + " | ".join([markdown_code(md_cell(family)), md_cell(description),
                ", ".join(markdown_code(md_cell(value)) for value in starts) or "—", "; ".join(links) or "—"]) + " |"
            (lines if candidates else unmatched).append(row)
        if unmatched:
            lines += ["", "## Registered entries without a documentation match", "",
                      "These registry identities remain visible for compatibility inspection; a registry entry alone does not establish a separate authoring diagram type.", "",
                      "| Registered entry | Description | Documented starters detected here | Documentation |",
                      "| --- | --- | --- | --- |", *unmatched]
        remaining = [name for name in docs if name not in used]
        if remaining:
            lines += ["", "## Additional upstream documentation", "", "| Topic | Description | Documentation |", "| --- | --- | --- |"]
            for name in remaining:
                body = pages.get(name, "")
                lines.append("| " + " | ".join([md_cell(page_title(body, name)),
                    md_cell(description_excerpt(body)), documentation_links(name, upstream)]) + " |")
    qualifications = [(name, page_introduction(pages[name])[1]) for name in docs]
    qualifications = [(name, notes) for name, notes in qualifications if notes]
    if qualifications:
        lines += ["", "## Source qualifications", ""]
        for name, notes in qualifications:
            lines.append(f"- [{md_label(page_title(pages[name], name))}]({page_link(name, pages[name], sidebar, commit, upstream)}): " + " ".join(md_cell(source_notice(note, name, upstream)) for note in notes))
    if upstream.get("source"):
        # A current source route stays useful even if the website changes its base.
        layouts = f"{UPSTREAM_REPO}/blob/HEAD/{docs_path.rsplit('/', 1)[0]}/config/layouts.md"
    else:
        layouts = LAYOUT_DOCS
    lines += ["", "## Source identity", "",
              f"Captured documentation SHA-256: {markdown_code(sha256(canonical_json(upstream_fixture_payload(upstream))))}.",
              f"Layout configuration: [official source]({layouts}).", ""]
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
    for path in (args.output, args.save_upstream):
        if path is not None and path.is_symlink():
            raise CatalogError(f"destination is a symbolic link: {path}; choose a regular output path")
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
