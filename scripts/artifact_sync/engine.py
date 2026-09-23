"""Execute ordinary commands against declared input snapshots."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import uuid

from .model import ArtifactError, Item, Manifest, Task, digest, json_bytes, load_manifest, matches, path_name
from .snapshots import Snapshot, materialize, read_item, safe_destination
from .publish import publish, publication_lock, same

RECEIPT_SCHEMA = "artifact-task.v1"


def install_termination_handler():
    """Let all CLI entry points unwind producer and publication ownership."""
    def interrupted(*_):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, interrupted)


def receipt(item, task):
    if item is None:
        return None
    try:
        value = json.loads(item.data)
        if not isinstance(value, dict) or value.get("schema") != RECEIPT_SCHEMA or value.get("task") != task.name:
            raise ValueError()
        if not isinstance(value["fingerprint"], str) or not isinstance(value["outputs"], dict):
            raise ValueError()
        for name, identity in value["outputs"].items():
            path_name(name)
            if not isinstance(identity, dict) or set(identity) != {"sha256", "mode"}:
                raise ValueError()
            if identity["mode"] not in {"100644", "100755", "120000"}:
                raise ValueError()
        return value
    except (TypeError, KeyError, ValueError) as exc:
        raise ArtifactError(f"invalid successful receipt for {task.name}",
                            "inspect the receipt; regenerate this task explicitly") from exc


def identities(items):
    return {name: item.identity for name, item in sorted(items.items())}


def covers_outputs(task, outputs):
    """Check declared fan-out independently of a receipt's own inventory."""
    for output in task.outputs:
        first = None
        for destination in output.destinations:
            members = ({p[len(destination) + 1:]: identity for p, identity in outputs.items()
                        if p.startswith(destination + "/")} if output.directory
                       else {"": outputs[destination]} if destination in outputs else {})
            if not members or first is not None and members != first:
                return False
            if output.executable is not None:
                expected_mode = "100755" if output.executable else "100644"
                if any(identity["mode"] not in {expected_mode, "120000"} for identity in members.values()):
                    return False
            first = members
    return True


def prepared_items(root, manifest, task, fingerprint):
    """Import only a complete result for the exact declared source identity."""
    saved_path = manifest.receipt_path(task.name)
    candidates = [root, *(p for p in sorted(root.iterdir()) if p.is_dir() and not p.is_symlink())]
    candidates = [p for p in candidates if safe_destination(p, saved_path).is_file()]
    if len(candidates) != 1:
        raise ArtifactError(f"{task.name}: prepared artifacts require one successful receipt",
                            f"supply the generated outputs and {saved_path} in the same artifact tree")
    tree = candidates[0]
    saved = receipt(read_item(safe_destination(tree, saved_path)), task)
    if (saved["fingerprint"] != fingerprint
            or saved.get("definition_digest") != digest(json_bytes(task.definition))
            or not covers_outputs(task, saved["outputs"])):
        raise ArtifactError(f"{task.name}: prepared receipt does not match the declared inputs and outputs")
    result = {}
    for name, identity in saved["outputs"].items():
        if not any(name == d and not output.directory or output.directory and name.startswith(d + "/")
                   for output in task.outputs for d in output.destinations):
            raise ArtifactError(f"{task.name}: prepared receipt contains an undeclared output: {name}")
        item = read_item(safe_destination(tree, name))
        if item is None or item.identity != identity:
            raise ArtifactError(f"{task.name}: prepared output identity differs: {name}")
        result[name] = item
    with tempfile.TemporaryDirectory(prefix="artifact-import-check-") as directory:
        materialize(Path(directory), result)
    return result


def task_inputs(snapshot, task, overlay):
    files = snapshot.files(task.inputs, task.optional_inputs, task.exclude, overlay)
    fingerprint = digest(json_bytes({"definition": task.definition, "inputs": identities(files)}))
    return files, fingerprint


def produced_items(work, task):
    result = {}
    for output in task.outputs:
        source = work / output.source
        if output.directory:
            if source.is_symlink() or not source.is_dir():
                raise ArtifactError(f"{task.name}: missing output directory {output.source}")
            paths = [p for p in sorted(source.rglob("*")) if p.is_file() or p.is_symlink()]
            if not paths:
                raise ArtifactError(f"{task.name}: empty promised output directory {output.source}")
        else:
            paths = [source]
        for file in paths:
            try:
                item = read_item(file)
            except OSError as exc:
                raise ArtifactError(f"{task.name}: cannot read output {output.source}") from exc
            if item is None:
                raise ArtifactError(f"{task.name}: missing promised output {output.source}")
            if output.executable is not None and item.mode != "120000":
                item = Item(item.data, "100755" if output.executable else "100644")
            if item.mode == "120000":
                try:
                    file.resolve(strict=True).relative_to(work)
                except (OSError, RuntimeError, ValueError) as exc:
                    raise ArtifactError(f"{task.name}: output symlink leaves the prepared workspace") from exc
            for destination in output.destinations:
                name = destination + "/" + file.relative_to(source).as_posix() if output.directory else destination
                path_name(name)
                if name in result:
                    raise ArtifactError(f"{task.name}: duplicate produced destination {name}")
                result[name] = item
    # Validate the symlink graph after fan-out, using the actual delivered layout.
    with tempfile.TemporaryDirectory(prefix="artifact-output-check-") as directory:
        materialize(Path(directory), result)
    return result


def command_environment(work, task):
    """Use the same command expansion and environment for execution and setup checks."""
    replace = {"{root}": str(work), "{output}": str(work / "_out"),
               "{python}": sys.executable, "{task}": task.name}
    def expanded(value):
        for key, replacement in replace.items():
            value = value.replace(key, replacement)
        return value
    command = [expanded(part) for part in task.command]
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("GIT_"):
            env.pop(key)
    env.update({key: expanded(value) for key, value in task.environment.items()})
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["ARTIFACT_TASK_PARAMETERS"] = json.dumps(task.parameters)
    env["ARTIFACT_SOURCE_ROOT"] = str(work)
    env["ARTIFACT_OUTPUT_ROOT"] = str(work / "_out")
    return command, env, expanded


def missing_tools(work, task):
    if not task.command:
        return []
    command, env, expanded = command_environment(work, task)
    required = list(dict.fromkeys([command[0], *(expanded(tool) for tool in task.tools)]))
    search = os.pathsep.join(str(work / entry) if not os.path.isabs(entry) else entry
                            for entry in env.get("PATH", os.defpath).split(os.pathsep))
    def available(tool):
        candidate = str(work / tool) if os.path.dirname(tool) and not os.path.isabs(tool) else tool
        return shutil.which(candidate, path=search)
    return [tool for tool in required if not available(tool)]


def run_command(work, task, logs):
    if not task.command:
        return
    command, env, _expanded = command_environment(work, task)
    missing = missing_tools(work, task)
    if missing:
        raise ArtifactError(f"{task.name}: required tool is unavailable: {missing[0]}",
                            "provide the declared tool and rerun; no dependency was installed")
    (work / "_out").mkdir(exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    process = None
    try:
        with (logs / "stdout.txt").open("wb") as stdout, (logs / "stderr.txt").open("wb") as stderr:
            process = subprocess.Popen(command, cwd=work, env=env, stdout=stdout, stderr=stderr,
                                       start_new_session=os.name == "posix")
            try:
                code = process.wait(timeout=task.timeout)
            except subprocess.TimeoutExpired as exc:
                raise ArtifactError(f"{task.name}: exceeded {task.timeout}s", f"inspect command logs in {logs}") from exc
        if code:
            raise ArtifactError(f"{task.name}: command exited {code}", f"inspect command logs in {logs}")
    except OSError as exc:
        raise ArtifactError(f"{task.name}: command could not start", f"check its runtime and command; logs: {logs}") from exc
    finally:
        if process is not None and process.poll() is None:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                process.wait()


def log_root(root):
    existing = sorted(p / "context" for p in root.glob(".local*") if (p / "context").is_dir())
    context = existing[0] if existing else root / "context"
    return context / "artifact-runs" / uuid.uuid4().hex


def sync(root: Path, *, source="worktree", selected=None, check=False, stage=False,
         replace=False, manifest_path="packaging/artifacts.toml", automatic=False, prepared=None):
    if stage and source != "index":
        raise ArtifactError("--stage requires --source index")
    if not check and source.startswith("commit:"):
        raise ArtifactError("committed revisions are read-only sources", "use check for outgoing revisions")
    if not check:
        # Recover an interrupted publication before interpreting its partial files.
        with publication_lock(root):
            pass
    snapshot = Snapshot(root, source)
    manifest_item = snapshot.get(manifest_path)
    if manifest_item is None:
        raise ArtifactError(f"manifest is absent from {source}: {manifest_path}",
                            "include the artifact manifest in the selected source")
    manifest = load_manifest(manifest_item.data, manifest_path)
    tasks = manifest.order(selected, automatic=automatic or not selected)
    # Freeze destination observations before producer commands start.
    observed_files = {}
    observed_directories = {}
    for task in tasks:
        saved_path = manifest.receipt_path(task.name)
        observed_files[saved_path] = snapshot.get(saved_path)
        for output in task.outputs:
            for destination in output.destinations:
                if output.directory:
                    observed_directories[destination] = snapshot.destination_files(destination)
                else:
                    observed_files[destination] = snapshot.get(destination)
    overlay: dict[str, Item | None] = {}
    changes: dict[str, Item | None] = {}
    results = []
    guards = []
    logs = log_root(root)
    for task in tasks:
        inputs, fingerprint = task_inputs(snapshot, task, overlay)
        imported = prepared_items(prepared, manifest, task, fingerprint) if prepared is not None else None
        saved_path = manifest.receipt_path(task.name)
        previous = receipt(snapshot.get(saved_path), task)
        if previous:
            retired = [name for name in previous["outputs"] if not any(
                name == destination or output.directory and name.startswith(destination + "/")
                for output in task.outputs for destination in output.destinations)]
            if retired:
                raise ArtifactError(f"{task.name}: receipt owns a retired destination: {retired[0]}",
                                    "review and remove the retired outputs and receipt together, then regenerate")
        promised = {}
        if previous:
            for name in previous["outputs"]:
                if not any(name == destination or output.directory and name.startswith(destination + "/")
                           for output in task.outputs for destination in output.destinations):
                    continue
                promised[name] = overlay.get(name) if name in overlay else snapshot.get(name)
        intact = previous is not None and bool(promised) and all(
            item is not None and item.identity == previous["outputs"][name] for name, item in promised.items())
        intact = intact and covers_outputs(task, previous["outputs"])
        # Unexpected files in a directory are also destination edits.
        if intact:
            for output in task.outputs:
                if output.directory:
                    for destination in output.destinations:
                        actual = snapshot.destination_files(destination)
                        if set(actual) != {p for p in previous["outputs"] if p.startswith(destination + "/")}:
                            intact = False
        current = task.cache and previous is not None and previous["fingerprint"] == fingerprint and intact
        if imported is not None and current and identities(imported) != previous["outputs"]:
            raise ArtifactError(f"{task.name}: prepared bytes differ for the same accepted inputs",
                                "investigate reproducibility before accepting different artifacts")
        guards.append((task, fingerprint))
        if current:
            overlay.update(promised)
            results.append({"task": task.name, "status": "current"})
            continue
        if check:
            why = "missing receipt" if previous is None else "changed inputs or task" if previous["fingerprint"] != fingerprint else "output drift"
            raise ArtifactError(f"{task.name}: {why}", f"run artifacts-sync for {task.name} from its maintained sources", code=1)
        if imported is not None:
            produced = imported
        else:
            with tempfile.TemporaryDirectory(prefix="artifact-task-") as directory:
                work = Path(directory)
                materialize(work, inputs)
                # Every producer can inspect its own declaration without treating unrelated rows as inputs.
                subset = {"version": 1, "task": task.name, "definition": task.definition}
                (work / "_task.json").write_bytes(json_bytes(subset))
                run_command(work, task, logs / task.name)
                produced = produced_items(work, task)
        old = previous["outputs"] if previous else {}
        for output in task.outputs:
            if output.directory:
                for destination in output.destinations:
                    extra = set(snapshot.destination_files(destination)) - set(old) - set(produced)
                    if extra and not replace:
                        raise ArtifactError(f"{task.name}: unowned file in output directory: {sorted(extra)[0]}",
                                            "preserve it or explicitly replace the owned output directory")
                    for name in extra:
                        changes[name] = None
                        overlay[name] = None
        for name in sorted(set(old) | set(produced)):
            before = overlay.get(name) if name in overlay else snapshot.get(name)
            after = produced.get(name)
            if not replace:
                known = name in old and before is not None and before.identity == old[name]
                identical = after is not None and after.same(before)
                if before is not None and not known and not identical:
                    raise ArtifactError(f"{task.name}: destination has manual changes: {name}",
                                        "preserve the edit; change the maintained source or use explicit sync --replace")
            if not same(before, after):
                changes[name] = after
            overlay[name] = after
        record = Item(json_bytes({"schema": RECEIPT_SCHEMA, "task": task.name,
                                 "fingerprint": fingerprint, "definition_digest": digest(json_bytes(task.definition)),
                                 "inputs": identities(inputs), "outputs": identities(produced)}))
        if not record.same(snapshot.get(saved_path)):
            changes[saved_path] = record
        overlay[saved_path] = record
        results.append({"task": task.name, "status": "imported" if imported is not None else "executed", "outputs": len(produced)})
    if not check:
        def guard():
            current_snapshot = Snapshot(root, source)
            if source == "index" and current_snapshot.index_bytes != snapshot.index_bytes:
                raise ArtifactError("the index changed while tasks ran", "retry; current staging is preserved")
            current_manifest = current_snapshot.get(manifest_path)
            if not manifest_item.same(current_manifest):
                raise ArtifactError("the manifest changed while tasks ran", "retry with the current declarations")
            # Reused dependency bytes in the overlay must not conceal live edits.
            # Observe the selected source, so index runs still allow unstaged inputs.
            for name, before in observed_files.items():
                if not same(before, current_snapshot.get(name)):
                    raise ArtifactError(f"destination changed during preparation: {name}",
                                        "preserve the concurrent edit and retry")
            for name, before in observed_directories.items():
                if identities(before) != identities(current_snapshot.destination_files(name)):
                    raise ArtifactError(f"output directory changed during preparation: {name}",
                                        "preserve the concurrent edit and retry")
            for task, fingerprint in guards:
                _files, fresh = task_inputs(current_snapshot, task, overlay)
                if fresh != fingerprint:
                    raise ArtifactError(f"{task.name}: an input changed while preparing", "retry with the current inputs")
        expected = {}
        for name in changes:
            actual = read_item(safe_destination(root, name))
            base = snapshot.get(name)
            if not same(actual, base) and not same(actual, changes[name]):
                message = "unstaged destination edit conflicts with generation" if stage else "destination changed during preparation"
                raise ArtifactError(f"{message}: {name}", "preserve the edit and retry")
            expected[name] = actual
        publish(root, changes, expected, index=snapshot.index_file if stage else None,
                original_index=snapshot.index_bytes, guard=guard)
    return {"source": snapshot.source, "tasks": results, "changed": sorted(changes),
            "logs": str(logs) if logs.exists() else None}
