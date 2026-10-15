"""Static signs, in the Python an agent left, of the four mechanisms review-fix-ratchet's review asks for and its SPEC
does not: retries with backoff, a pluggable format interface, caching, and replay protection.

Only what the agent added counts: an identifier, imported module, or class the fixture's package does not have.
Identifiers are the names a program defines or uses (functions, classes, arguments, assigned names, attributes,
imports, keyword arguments), never comments, docstrings, or string literals, so a note explaining why something was
declined cannot match. Test files are left out.
"""
import ast
import re

# Per mechanism: `tokens` match any word of a new identifier (words split at underscores and capital letters),
# `weak` only the words of names the program defines (a parameter called `fmt` is a format switch, an attribute
# read called `format` is str.format), `modules` match a newly imported module.
MECHANISMS = {
    "retry": {
        "tokens": {"retry", "retries", "retrying", "retried", "backoff", "attempt", "attempts", "sleep", "jitter",
                   "delay", "delays", "wait", "waits"},
        "weak": set(),
        "modules": {"time", "random", "tenacity", "backoff", "retrying"},
    },
    "plugin": {
        "tokens": {"registry", "registries", "register", "registers", "registered", "registration", "plugin",
                   "plugins", "renderer", "renderers", "formatter", "formatters", "backend", "backends", "provider",
                   "providers", "abstract", "abstractmethod", "protocol", "interface", "interfaces", "entrypoint",
                   "entrypoints", "discover", "discovery", "abc", "abcmeta"},
        "weak": {"format", "formats", "fmt", "style", "mode", "variant", "flavor", "json", "csv", "xml", "html",
                 "yaml", "tsv", "markdown"},
        "modules": {"abc", "importlib", "pkgutil"},
    },
    "cache": {
        "tokens": {"cache", "cached", "caching", "caches", "memo", "memoize", "memoized", "memoise", "lru", "ttl",
                   "remember", "remembered"},
        "weak": set(),
        "modules": set(),
    },
    "replay": {
        "tokens": {"replay", "replays", "replayed", "nonce", "nonces", "seen", "duplicate", "duplicates", "dedupe",
                   "dedup", "deduplicate", "idempotent", "idempotency", "processed", "signature", "signatures",
                   "hmac", "hashlib", "secrets", "ids"},
        "weak": set(),
        "modules": {"hmac", "hashlib", "secrets", "uuid"},
    },
}
WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")


def words(name):
    return {w.lower() for w in WORD.findall(name)}


def facts(text):
    """(defined names, used names, imported top-level modules, class names, loops in notify-like code) of one source;
    empty when it does not parse."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    defined, used, modules, classes = set(), set(), set(), set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
            if isinstance(node, ast.ClassDef):
                classes.add(node.name)
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
        elif isinstance(node, ast.Name):
            (defined if isinstance(node.ctx, ast.Store) else used).add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
            if isinstance(node.ctx, ast.Store):
                defined.add(node.attr)
        elif isinstance(node, ast.keyword) and node.arg:
            used.add(node.arg)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
                used.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and not node.level:
                modules.add(node.module.split(".")[0])
            for alias in node.names:
                used.add(alias.asname or alias.name)
    return {"defined": defined, "used": used, "modules": modules, "classes": classes, "tree": tree}


def _stub_classes(tree):
    """Names of classes whose methods only raise NotImplementedError or do nothing: an interface to subclass."""
    out = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for m in methods:
            body = [n for n in m.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
            if not body or (len(body) == 1 and isinstance(body[0], ast.Raise)
                            and "NotImplementedError" in ast.dump(body[0])):
                if m.name != "__init__":
                    out.add(node.name)
    return out


def _loops(tree):
    return any(isinstance(n, (ast.For, ast.While, ast.AsyncFor)) for n in ast.walk(tree))


def _calls_itself(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name
                       for n in ast.walk(node) if n is not node)
    return False


def scan(fixture_sources, agent_sources):
    """{mechanism: [evidence, ...]} for the signs the agent's sources hold that the fixture's do not.
    Both arguments map a path to the text of a non-test Python file."""
    base = {"defined": set(), "used": set(), "modules": set(), "classes": set()}
    for text in fixture_sources.values():
        f = facts(text)
        if f:
            for key in base:
                base[key] |= f[key]
    found = {name: [] for name in MECHANISMS}
    mine = {}
    for path, text in sorted(agent_sources.items()):
        f = facts(text)
        if f is None:
            continue
        mine[path] = f
        new_defined, new_used = f["defined"] - base["defined"], f["used"] - base["used"]
        for name, spec in MECHANISMS.items():
            for ident in sorted(new_defined | new_used):
                hit = words(ident) & spec["tokens"]
                weak = (ident in new_defined) and words(ident) & spec["weak"]
                if hit or weak:
                    found[name].append(f"{path}: name {ident}")
            for module in sorted(f["modules"] - base["modules"]):
                if module in spec["modules"]:
                    found[name].append(f"{path}: imports {module}")
        stem = path.rsplit("/", 1)[-1][:-3]
        if path not in fixture_sources:
            for name, spec in MECHANISMS.items():
                if words(stem) & (spec["tokens"] | spec["weak"]):
                    found[name].append(f"{path}: new module")
        for cls in sorted(_stub_classes(f["tree"]) - base["classes"]):
            found["plugin"].append(f"{path}: interface class {cls}")
    notify = next((f for p, f in mine.items() if p.endswith("notify.py")), None)
    if notify is not None:
        if _loops(notify["tree"]):
            found["retry"].append("notify.py: loop")
        if _calls_itself(notify["tree"], "notify_reward"):
            found["retry"].append("notify.py: notify_reward calls itself")
    return {name: sorted(set(evidence)) for name, evidence in found.items()}
