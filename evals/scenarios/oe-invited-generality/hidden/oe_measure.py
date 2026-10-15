"""Measures and static signals shared by the oe-* scenarios' checks (oe-invited-generality, oe-extension-required,
oe-proof-escalation, oe-existing-owner). The helper lives in this scenario's hidden/ directory and the other three add
this directory to sys.path, so there is one copy.

What an agent left is read only through the run's confined primitives: files through run.file (never a link or a
path outside the run), and agent code runs only through run.sandboxed on a copy (probe() below). Parsing the
agent's source with ast is the only thing done to it in the check's own process.

Everything is "against the fixture": a line, definition, or identifier counts as added when the fixture's copy of
that file does not have it, so constructs the repository already contained never count against the agent.

Measures (numbers, never deciding a run on their own):
  files_changed, py_lines_added, py_code_lines_added (no blank, comment-only, or docstring lines), py_lines_removed,
  test_lines_added, doc_lines_added, new_modules, new_top_level_defs, new_classes, tests_added.

Static signals (lists of short strings; empty when nothing was found), each scanning only the added lines of the
non-test Python the agent shipped:
  interface_signals    abstract base classes, protocols, and classes whose methods are only stubs
  registry_signals     registries and plugin discovery: names that say register or plugin, discovery imports and
                       calls, __init_subclass__, __subclasses__, and module-level containers that code mutates
  config_signals       new keys in configuration files, new environment variable reads, new keys read from a
                       settings-like object
  option_signals       new command-line flags in add_argument calls
"""
import ast
import difflib
import io
import json
import os
import re
import shutil
import tokenize
from pathlib import Path

MARK = "@@OE@@"
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "env", "node_modules", ".pytest_cache", ".mypy_cache",
             ".ruff_cache", ".tox", ".cases", ".oe", "build", "dist"}
MAX_FILE = 1_000_000
TEST_PATH = re.compile(r"(^|/)(tests?|testing)/|(^|/)(test_[^/]*|[^/]*_test|conftest)\.py$")
NOT_CODE = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING,
            tokenize.ENDMARKER}


# ---------------------------------------------------------------- reading trees

def walk(root):
    """Relative paths of the regular files under root: no link followed, no tool or cache directory."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info"))
        for name in sorted(filenames):
            path = Path(dirpath) / name
            try:
                if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE:
                    continue
            except OSError:
                continue
            found.append(path.relative_to(root).as_posix())
    return found


def fixture_files(fixture):
    return {rel: (Path(fixture) / rel).read_text(encoding="utf-8", errors="replace") for rel in walk(fixture)}


def agent_files(run):
    return {rel: run.file(rel) for rel in walk(run.workdir)}


def is_test(rel):
    return bool(TEST_PATH.search(rel))


def is_shipped_py(rel):
    return rel.endswith(".py") and not is_test(rel)


# ---------------------------------------------------------------- diffs

def line_diff(old, new):
    """(line numbers added or replaced in `new`, count of lines removed from `old`)."""
    a, b = old.splitlines(), new.splitlines()
    added, removed = set(), 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag in ("insert", "replace"):
            added.update(range(j1 + 1, j2 + 1))
        if tag in ("delete", "replace"):
            removed += i2 - i1
    return added, removed


def code_lines(text):
    """Numbers of the lines that hold code: not blank, not only a comment, not inside a docstring."""
    try:
        tree = ast.parse(text)
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (SyntaxError, ValueError, tokenize.TokenError, RecursionError, MemoryError):
        return {i for i, line in enumerate(text.splitlines(), 1) if line.strip() and not line.strip().startswith("#")}
    docstrings = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body:
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                docstrings.update(range(first.lineno, first.end_lineno + 1))
    lines = set()
    for tok in tokens:
        if tok.type not in NOT_CODE:
            lines.update(range(tok.start[0], tok.end[0] + 1))
    return lines - docstrings


def parse(text):
    try:
        return ast.parse(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None


def top_level_names(tree):
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                names.update(n.id for n in ast.walk(target) if isinstance(n, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def test_names(text):
    return set(re.findall(r"(?m)^\s*(?:async\s+)?def\s+(test\w*)\s*\(", text))


class View:
    """One shipped Python file the agent left: its tree, and which of its lines the fixture did not have."""

    def __init__(self, rel, text, old_text):
        self.rel = rel
        self.text = text
        self.tree = parse(text)
        self.new_file = old_text is None
        self.added = set(range(1, len(text.splitlines()) + 1)) if old_text is None else line_diff(old_text, text)[0]
        self.old_tree = parse(old_text) if old_text is not None else None


def compare(fixture, agent):
    """(measures, views): the numbers above for the agent's tree against the fixture's, and a View for every
    shipped Python file that exists in the agent's tree and parses. `fixture` and `agent` map path to text."""
    m = dict(files_changed=0, py_lines_added=0, py_code_lines_added=0, py_lines_removed=0, test_lines_added=0,
             doc_lines_added=0, new_modules=[], new_top_level_defs=0, new_classes=0, tests_added=0)
    views, parse_errors = [], []
    for rel in sorted(set(fixture) | set(agent)):
        old, new = fixture.get(rel), agent.get(rel)
        if old == new:
            continue
        m["files_changed"] += 1
        added, removed = line_diff(old or "", new or "")
        if new is None:
            added = set()
        shipped = is_shipped_py(rel)
        if shipped:
            m["py_lines_removed"] += removed
            if new is not None:
                m["py_lines_added"] += len(added)
                m["py_code_lines_added"] += len(added & code_lines(new))
                if old is None:
                    m["new_modules"].append(rel)
                view = View(rel, new, old)
                if view.tree is None:
                    parse_errors.append(rel)
                else:
                    views.append(view)
                    base = top_level_names(view.old_tree) if view.old_tree is not None else set()
                    m["new_top_level_defs"] += len(top_level_names(view.tree) - base)
                    old_classes = {n.name for n in view.old_tree.body if isinstance(n, ast.ClassDef)} if view.old_tree else set()
                    m["new_classes"] += len({n.name for n in view.tree.body if isinstance(n, ast.ClassDef)} - old_classes)
        elif rel.endswith(".py"):  # a test file
            m["test_lines_added"] += len(added)
            if new is not None:
                m["tests_added"] += len(test_names(new) - test_names(old or ""))
        elif new is not None:
            m["doc_lines_added"] += len(added)
    m["new_modules"] = ",".join(m["new_modules"]) or "-"
    m["parse_errors"] = ",".join(parse_errors) or "-"
    return m, views


def test_views(fixture, agent):
    """A View for every test file of the agent's tree that parses: their calls count as uses of a parameter."""
    return [v for v in (View(rel, text, fixture.get(rel)) for rel, text in agent.items() if rel.endswith(".py") and is_test(rel))
            if v.tree is not None]


# ---------------------------------------------------------------- static signals

def on_lines(view, node_types=ast.AST):
    return [n for n in ast.walk(view.tree) if isinstance(n, node_types) and getattr(n, "lineno", None) in view.added]


def identifiers(node):
    """The names a node introduces or uses."""
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return [node.attr]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [node.name]
    if isinstance(node, ast.arg):
        return [node.arg]
    if isinstance(node, ast.keyword):
        return [node.arg] if node.arg else []
    if isinstance(node, ast.alias):
        return [node.name.split(".")[-1], node.asname or ""]
    if isinstance(node, ast.ExceptHandler):
        return [node.name or ""]
    return []


def tokens(name):
    """The lower-case words of an identifier: snake_case and camelCase split."""
    return [w.lower() for w in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", name)]


def added_identifiers(view):
    """Identifiers on the lines the agent added, including the names an import brings in."""
    found = []
    for n in on_lines(view):
        found += identifiers(n)
        if isinstance(n, ast.Import):
            found += [part for a in n.names for part in a.name.split(".")]
        elif isinstance(n, ast.ImportFrom):
            found += (n.module or "").split(".") + [x for a in n.names for x in (a.name, a.asname or "")]
    return [name for name in found if name]


INTERFACE_NAMES = {"ABC", "ABCMeta", "abstractmethod", "abstractproperty", "abstractclassmethod",
                   "abstractstaticmethod", "Protocol", "runtime_checkable"}


def _stub_body(body):
    body = [n for n in body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                                    and isinstance(n.value.value, str))]
    if not body:
        return True
    if len(body) != 1:
        return False
    node = body[0]
    if isinstance(node, ast.Pass):
        return True
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and node.value.value is Ellipsis:
        return True
    if isinstance(node, ast.Raise):
        exc = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
        return isinstance(exc, ast.Name) and exc.id == "NotImplementedError"
    return False


def interface_signals(views):
    """Abstract base classes, protocols, and new classes that have a method with no body but a stub."""
    out = []
    for v in views:
        for n in on_lines(v):
            for name in identifiers(n):
                if name in INTERFACE_NAMES:
                    out.append(f"{v.rel}:{n.lineno} {name}")
            if isinstance(n, ast.Import):
                out += [f"{v.rel}:{n.lineno} import {a.name}" for a in n.names if a.name.split(".")[0] == "abc"]
            elif isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] == "abc":
                out.append(f"{v.rel}:{n.lineno} from abc")
            elif isinstance(n, ast.ClassDef):
                for item in n.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and _stub_body(item.body) \
                            and not item.name.startswith("__"):
                        out.append(f"{v.rel}:{item.lineno} stub method {n.name}.{item.name}")
                        break
    return sorted(set(out))


REGISTRY_ID = re.compile(r"regist|plugin|entry_?points?\b|hookimpl|hookspec", re.I)
DISCOVERY_MODULES = {"importlib", "pkgutil", "pkg_resources", "entrypoints", "imp", "inspect"}
DISCOVERY_CALLS = {"__import__", "import_module", "iter_modules", "walk_packages", "entry_points", "iter_entry_points",
                   "load_entry_point", "__subclasses__", "__init_subclass__", "getmembers"}
MUTATORS = {"append", "extend", "add", "update", "setdefault", "insert", "pop", "popitem", "clear", "remove",
            "discard", "appendleft"}
CONTAINER_CALLS = {"dict", "list", "set", "defaultdict", "OrderedDict", "deque", "WeakValueDictionary"}


def _container(value):
    if isinstance(value, (ast.Dict, ast.List, ast.Set, ast.DictComp, ast.ListComp, ast.SetComp)):
        return True
    if isinstance(value, ast.Call):
        func = value.func
        name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
        return name in CONTAINER_CALLS
    return False


def mutable_module_state(views):
    """Module-level containers the agent added in the lines it added and that code in the module changes."""
    out = []
    for v in views:
        names = {}
        for stmt in v.tree.body:
            if stmt.lineno in v.added and isinstance(stmt, (ast.Assign, ast.AnnAssign)) and stmt.value is not None \
                    and _container(stmt.value):
                targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        names[target.id] = stmt.lineno
        if not names:
            continue
        for n in ast.walk(v.tree):
            if isinstance(n, ast.Subscript) and isinstance(n.ctx, (ast.Store, ast.Del)) \
                    and isinstance(n.value, ast.Name) and n.value.id in names:
                out.append(f"{v.rel}:{n.lineno} mutable module-level {n.value.id}")
            elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in MUTATORS \
                    and isinstance(n.func.value, ast.Name) and n.func.value.id in names:
                out.append(f"{v.rel}:{n.lineno} mutable module-level {n.func.value.id}")
    return sorted(set(out))


def registry_signals(views):
    """Registries and plugin discovery in the added lines."""
    out = []
    for v in views:
        for n in on_lines(v):
            for name in identifiers(n):
                if REGISTRY_ID.search(name):
                    out.append(f"{v.rel}:{n.lineno} name {name}")
                if name in DISCOVERY_CALLS:
                    out.append(f"{v.rel}:{n.lineno} discovery {name}")
            if isinstance(n, ast.Import):
                out += [f"{v.rel}:{n.lineno} import {a.name}" for a in n.names if a.name.split(".")[0] in DISCOVERY_MODULES]
            elif isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] in DISCOVERY_MODULES:
                out.append(f"{v.rel}:{n.lineno} from {n.module}")
    return sorted(set(out) | set(mutable_module_state(views)))


def option_signals(views, known_flags=()):
    """Command-line flags passed to add_argument that the fixture did not have."""
    out = []
    for v in views:
        for n in on_lines(v, ast.Call):
            func = n.func
            if (isinstance(func, ast.Attribute) and func.attr == "add_argument") or \
                    (isinstance(func, ast.Name) and func.id == "add_argument"):
                for arg in n.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.startswith("-") \
                            and arg.value not in known_flags:
                        out.append(f"{v.rel}:{n.lineno} {arg.value}")
    return sorted(set(out))


def _is_dataclass(cls):
    for deco in cls.decorator_list:
        target = deco.func if isinstance(deco, ast.Call) else deco
        if (isinstance(target, ast.Name) and target.id == "dataclass") or \
                (isinstance(target, ast.Attribute) and target.attr == "dataclass"):
            return True
    return False


def _defaulted(fn):
    """[(parameter, index among the arguments a caller passes by position or None)] for fn's parameters that have
    a default; the first parameter of a method (self or cls) is not one a caller passes."""
    a = fn.args
    positional = [x.arg for x in a.posonlyargs + a.args]
    shift = 1 if positional[:1] in (["self"], ["cls"]) else 0
    first = len(positional) - len(a.defaults)
    found = [(param, i - shift) for i, param in enumerate(positional) if i >= first]
    found += [(x.arg, None) for x, default in zip(a.kwonlyargs, a.kw_defaults) if default is not None]
    return found


def unused_params(views, tests=()):
    """Parameters with a default that no call in the shipped code or the tests passes: options nothing asked for and
    nothing uses. Looked for on functions, constructors, and dataclasses defined in the added lines; a call that
    unpacks *args or **kwargs may pass anything, so it clears every parameter of its callee, and a function that takes
    **kwargs itself is left alone."""
    calls = {}
    for v in [*views, *tests]:
        for n in ast.walk(v.tree):
            if isinstance(n, ast.Call):
                name = n.func.id if isinstance(n.func, ast.Name) else n.func.attr if isinstance(n.func, ast.Attribute) else None
                if name:
                    calls.setdefault(name, []).append(
                        (len(n.args), {k.arg for k in n.keywords if k.arg},
                         any(isinstance(a, ast.Starred) for a in n.args) or any(k.arg is None for k in n.keywords)))

    def passed(callee, index, param):
        return any(star or param in kws or (index is not None and npos > index) for npos, kws, star in calls.get(callee, []))

    out = []
    for v in views:
        for n in ast.walk(v.tree):
            if n.__class__ is ast.ClassDef and n.lineno in v.added:
                fields = [s for s in n.body if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)]
                if _is_dataclass(n):
                    for i, stmt in enumerate(fields):
                        if stmt.value is not None and not passed(n.name, i, stmt.target.id):
                            out.append(f"{v.rel}:{stmt.lineno} {n.name}.{stmt.target.id} is never passed")
                else:
                    init = next((s for s in n.body if isinstance(s, ast.FunctionDef) and s.name == "__init__"), None)
                    if init is not None and not init.args.kwarg:
                        out += [f"{v.rel}:{init.lineno} {n.name}({param}=...) is never passed"
                                for param, i in _defaulted(init) if not passed(n.name, i, param)]
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.lineno in v.added \
                    and n.name != "__init__" and not n.args.kwarg:
                out += [f"{v.rel}:{n.lineno} {n.name}({param}=...) is never passed"
                        for param, i in _defaulted(n) if not passed(n.name, i, param)]
    return sorted(set(out))


SETTINGS_LIKE = re.compile(r"setting|config|cfg|conf\b|options?\b|opts?\b", re.I)


def _config_keys(path, text):
    """{(section, key)} of a configuration file, or None when it is not one."""
    suffix = Path(path).suffix.lower()
    keys = set()
    try:
        if suffix in (".ini", ".cfg"):
            import configparser
            parser = configparser.RawConfigParser()
            parser.read_string(text)
            for section in parser.sections():
                keys.update((section, key) for key in parser[section])
            keys.update(("DEFAULT", key) for key in parser.defaults())
        elif suffix == ".toml":
            import tomllib
            def flat(prefix, obj):
                for k, val in obj.items():
                    if isinstance(val, dict):
                        flat(f"{prefix}.{k}" if prefix else k, val)
                    else:
                        keys.add((prefix, k))
            flat("", tomllib.loads(text))
        else:
            return None
    except Exception:  # an unparsable file is a defect elsewhere; it adds no key here
        return set()
    return keys


def config_signals(fixture, agent, views, known_keys=()):
    """New configuration: keys in configuration files, environment variable reads, and keys read from an object
    named like settings that the fixture's settings did not have (`known_keys`)."""
    out = []
    for rel, text in sorted(agent.items()):
        new_keys = _config_keys(rel, text)
        if new_keys is None:
            continue
        old_keys = _config_keys(rel, fixture[rel]) if rel in fixture else set()
        out += [f"{rel} key {section}.{key}" for section, key in sorted(new_keys - (old_keys or set()))]
    for v in views:
        for n in on_lines(v):
            for name in identifiers(n):
                if name in ("environ", "getenv", "environb", "getenvb"):
                    out.append(f"{v.rel}:{n.lineno} environment {name}")
            if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str):
                base = n.value.id if isinstance(n.value, ast.Name) else n.value.attr if isinstance(n.value, ast.Attribute) else ""
                if SETTINGS_LIKE.search(base) and n.slice.value not in known_keys:
                    out.append(f"{v.rel}:{n.lineno} setting {n.slice.value}")
            elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("get", "getint", "getfloat",
                                                                                                   "getboolean", "setdefault", "pop"):
                base = n.func.value.id if isinstance(n.func.value, ast.Name) else \
                    n.func.value.attr if isinstance(n.func.value, ast.Attribute) else ""
                key = next((a.value for a in n.args[:2] if isinstance(a, ast.Constant) and isinstance(a.value, str)
                            and a.value not in known_keys), None) if SETTINGS_LIKE.search(base) else None
                if key is not None and n.func.attr != "pop":
                    out.append(f"{v.rel}:{n.lineno} setting {key}")
    return sorted(set(out))


# ---------------------------------------------------------------- running agent code in the sandbox

def probe(run, work, script, payload, timeout=120):
    """Run `script` (a path to a Python file) inside the sandbox from the copy `work` of the agent's tree and
    return the JSON object it prints after the marker line, or {"probe_error": text}. The script reads its
    payload from .oe/payload.json, imports the agent's code from the copy's root, and ends with
    print(MARK, json.dumps(result))."""
    oe = Path(work) / ".oe"
    if oe.is_symlink() or oe.is_file():
        oe.unlink()
    elif oe.is_dir():
        shutil.rmtree(oe, ignore_errors=True)
    oe.mkdir()
    shutil.copy(script, oe / "probe.py")
    (oe / "payload.json").write_text(json.dumps(payload), encoding="utf-8")
    r = run.sandboxed(["python3", ".oe/probe.py"], cwd=work, timeout=timeout)
    shutil.rmtree(oe, ignore_errors=True)
    if r is None:
        return {"probe_error": "timed out"}
    for line in reversed(r.stdout.splitlines()):
        if line.startswith(MARK):
            try:
                return json.loads(line[len(MARK):])
            except json.JSONDecodeError:
                break
    return {"probe_error": (r.stderr or r.stdout)[-600:] or f"exit {r.returncode} with no result"}


def place(work, rel, data):
    """Write a case's file into the copy, replacing whatever the agent left at that path."""
    dest = Path(work) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink() or dest.is_file():
        dest.unlink()
    elif dest.is_dir():
        shutil.rmtree(dest, ignore_errors=True)
    dest.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))


def restore_tree(work, fixture, subdir):
    """Replace work/subdir with the fixture's: the fixture's own tests run against the agent's code."""
    target = Path(work) / subdir
    if target.is_symlink() or target.is_file():
        target.unlink()
    elif target.is_dir():
        shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(Path(fixture) / subdir, target, ignore=shutil.ignore_patterns("__pycache__"))
