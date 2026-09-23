"""Language-independent task declarations and content identities."""
from __future__ import annotations

from dataclasses import dataclass
import fnmatch
from functools import lru_cache
import hashlib
import json
from pathlib import PurePosixPath
import re
import tomllib

SCHEMA = 1


class ArtifactError(Exception):
    """An expected failure with a recovery action."""

    def __init__(self, message: str, hint: str = "inspect the task declaration and retry", code: int = 2):
        super().__init__(message)
        self.hint = hint
        self.code = code


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n").encode()


def path_name(value: str, *, pattern: bool = False) -> str:
    if (not isinstance(value, str) or not value or "\\" in value or ":" in value
            or any(ord(c) < 32 for c in value) or value.startswith("/")
            or any(p in ("", ".", "..") for p in value.split("/"))):
        raise ArtifactError(f"unsafe repository path: {value!r}")
    if value.split("/")[0] == ".git":
        raise ArtifactError("Git internals cannot be task paths")
    if not pattern and any(c in value for c in "*?[]"):
        raise ArtifactError(f"output path must be literal: {value}")
    return value


def matches(name: str, pattern: str) -> bool:
    if not any(c in pattern for c in "*?["):
        return name == pattern or name.startswith(pattern.rstrip("/") + "/")
    names, patterns = name.split("/"), pattern.split("/")
    @lru_cache(maxsize=None)
    def visit(i, j):
        if j == len(patterns):
            return i == len(names)
        if patterns[j] == "**":
            return visit(i, j + 1) or i < len(names) and visit(i + 1, j)
        return i < len(names) and fnmatch.fnmatchcase(names[i], patterns[j]) and visit(i + 1, j + 1)
    return visit(0, 0)


@dataclass(frozen=True)
class Item:
    data: bytes
    mode: str = "100644"

    @property
    def identity(self):
        return {"sha256": digest(self.data), "mode": self.mode}

    def same(self, other: Item | None) -> bool:
        return other is not None and self.mode == other.mode and self.data == other.data


@dataclass(frozen=True)
class Output:
    source: str
    destinations: tuple[str, ...]
    directory: bool = False
    executable: bool | None = None


@dataclass(frozen=True)
class Task:
    name: str
    inputs: tuple[str, ...]
    optional_inputs: tuple[str, ...]
    exclude: tuple[str, ...]
    command: tuple[str, ...]
    needs: tuple[str, ...]
    outputs: tuple[Output, ...]
    automatic: bool
    cache: bool
    environment: dict[str, str]
    tools: tuple[str, ...]
    timeout: int
    parameters: dict
    receipt: str | None = None

    @property
    def definition(self) -> dict:
        return {
            "inputs": sorted(self.inputs), "optional_inputs": sorted(self.optional_inputs),
            "exclude": sorted(self.exclude), "command": self.command, "needs": sorted(self.needs),
            "outputs": [dict(source=o.source, destinations=o.destinations,
                             directory=o.directory, executable=o.executable) for o in self.outputs],
            "automatic": self.automatic, "cache": self.cache, "environment": self.environment,
            "tools": sorted(self.tools), "timeout": self.timeout, "parameters": self.parameters,
            "receipt": self.receipt,
        }


@dataclass(frozen=True)
class Manifest:
    path: str
    receipts: str
    tasks: dict[str, Task]
    payload: bytes

    def receipt_path(self, name: str) -> str:
        return self.tasks[name].receipt or f"{self.receipts}/{name}.json"

    def order(self, selected: list[str] | None, *, automatic: bool = True) -> list[Task]:
        names = list(selected) if selected else [n for n, t in self.tasks.items() if not automatic or t.automatic]
        result: list[Task] = []
        done: set[str] = set()
        pending: set[str] = set()

        def visit(name):
            if name not in self.tasks:
                raise ArtifactError(f"unknown task: {name}", "valid tasks: " + ", ".join(sorted(self.tasks)))
            if name in pending:
                raise ArtifactError(f"task dependency cycle at {name}")
            if name in done:
                return
            task = self.tasks[name]
            if automatic and not task.automatic:
                raise ArtifactError(f"automatic work depends on explicit task {name}",
                                    "invoke that task explicitly and retain its outputs as inputs")
            pending.add(name)
            for parent in task.needs:
                visit(parent)
            pending.remove(name)
            done.add(name)
            result.append(task)

        for name in names:
            visit(name)
        return result


def strings(value, field, *, required=False):
    if value is None and not required:
        return ()
    if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value):
        raise ArtifactError(f"{field} must be an array of nonempty strings")
    if required and not value:
        raise ArtifactError(f"{field} must not be empty")
    return tuple(value)


def load_manifest(payload: bytes, path="packaging/artifacts.toml") -> Manifest:
    try:
        data = tomllib.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ArtifactError("invalid artifact manifest", "supply UTF-8 TOML") from exc
    if data.get("version") != SCHEMA or not isinstance(data.get("tasks"), dict):
        raise ArtifactError("manifest requires version = 1 and task tables")
    unknown = set(data) - {"version", "receipt_dir", "tasks"}
    if unknown:
        raise ArtifactError("unknown manifest fields: " + ", ".join(sorted(unknown)))
    receipts = path_name(data.get("receipt_dir", "packaging/receipts"))
    tasks = {}
    ownership = []
    allowed = {"inputs", "optional_inputs", "exclude", "command", "needs", "outputs",
               "automatic", "cache", "environment", "tools", "timeout", "parameters", "receipt"}
    for name, value in data["tasks"].items():
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", name) or not isinstance(value, dict):
            raise ArtifactError(f"invalid task name or declaration: {name!r}")
        if set(value) - allowed:
            raise ArtifactError(f"{name}: unknown fields: " + ", ".join(sorted(set(value) - allowed)))
        inputs = strings(value.get("inputs"), f"{name}.inputs", required=True)
        optional = strings(value.get("optional_inputs"), f"{name}.optional_inputs")
        exclude = strings(value.get("exclude"), f"{name}.exclude")
        for item in (*inputs, *optional, *exclude):
            path_name(item, pattern=True)
        command = strings(value.get("command"), f"{name}.command")
        needs = strings(value.get("needs"), f"{name}.needs")
        tools = strings(value.get("tools"), f"{name}.tools")
        environment = value.get("environment", {})
        if not isinstance(environment, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                                                    for k, v in environment.items()):
            raise ArtifactError(f"{name}.environment requires string values")
        if any(k in {"HOME", "CODEX_HOME", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"} for k in environment):
            raise ArtifactError(f"{name}: environment cannot replace host identity or Git selection")
        for key in ("automatic", "cache"):
            if key in value and type(value[key]) is not bool:
                raise ArtifactError(f"{name}.{key} must be a boolean")
        timeout = value.get("timeout", 600)
        if type(timeout) is not int or not 1 <= timeout <= 86400:
            raise ArtifactError(f"{name}.timeout must be 1..86400 seconds")
        parameters = value.get("parameters", {})
        if not isinstance(parameters, dict):
            raise ArtifactError(f"{name}.parameters must be a table")
        receipt_path = path_name(value["receipt"]) if "receipt" in value else None
        raw_outputs = value.get("outputs")
        if not isinstance(raw_outputs, list) or not raw_outputs:
            raise ArtifactError(f"{name}.outputs must be a nonempty array of tables")
        outputs = []
        for output in raw_outputs:
            if not isinstance(output, dict) or set(output) - {"source", "destinations", "directory", "executable"}:
                raise ArtifactError(f"{name}: invalid output declaration")
            source = path_name(output.get("source"))
            destinations = strings(output.get("destinations"), f"{name}.destinations", required=True)
            directory = output.get("directory", False)
            executable = output.get("executable")
            if type(directory) is not bool or executable is not None and type(executable) is not bool:
                raise ArtifactError(f"{name}: directory/executable must be boolean")
            for destination in destinations:
                path_name(destination)
                if destination == path or destination == receipts or destination.startswith(receipts + "/"):
                    raise ArtifactError(f"{name}: output collides with manifest or receipts")
                for owner, existing, is_dir in ownership:
                    if (destination == existing or is_dir and destination.startswith(existing + "/")
                            or directory and existing.startswith(destination + "/")):
                        raise ArtifactError(f"output ownership collision: {owner} and {name} at {destination}")
                ownership.append((name, destination, directory))
            outputs.append(Output(source, destinations, directory, executable))
        tasks[name] = Task(name, inputs, optional, exclude, command, needs, tuple(outputs),
                           value.get("automatic", True), value.get("cache", True), environment,
                           tools, timeout, parameters, receipt_path)
    result = Manifest(path, receipts, tasks, payload)
    receipt_paths = [result.receipt_path(name) for name in tasks]
    if len(set(receipt_paths)) != len(receipt_paths):
        raise ArtifactError("tasks must have distinct receipt paths")
    for receipt_path in receipt_paths:
        if any(receipt_path == destination or directory and receipt_path.startswith(destination + "/")
               for _name, destination, directory in ownership):
            raise ArtifactError("a receipt collides with an artifact destination")
    result.order(list(tasks), automatic=False)
    return result
