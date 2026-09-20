#!/usr/bin/env python3
"""Prepare scoped input copies and output locations; never dispatch participants."""

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import stat
import sys
import tempfile
import uuid


class PreparationError(Exception):
    def __init__(self, message, hint="see --help and references/workspaces.md", code=2):
        super().__init__(message)
        self.hint = hint
        self.code = code


def object_fields(value, required, label):
    if not isinstance(value, dict) or set(value) != set(required):
        raise PreparationError("{} requires exactly these fields: {}".format(label, ", ".join(required)))


def identifier(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value):
        raise PreparationError(label + " must be 1-64 letters, digits, underscores or hyphens, starting with a letter or digit")
    return value


def relative_path(value, label):
    if (not isinstance(value, str) or not value or "\\" in value or ":" in value
            or any(ord(char) < 32 for char in value)
            or any(part in ("", ".", "..") for part in value.split("/"))):
        raise PreparationError(label + " must be a relative slash-separated path without empty, '.' or '..' components")
    path = PurePosixPath(value)
    if path.is_absolute():
        raise PreparationError(label + " must be relative")
    return path


def within(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def signature(info):
    return (info.st_mode, info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def inventory(source, destination):
    """Never walk through source links; selected targets are checked per group."""
    result = []

    def visit(path, target):
        info = path.lstat()
        link = os.readlink(path) if stat.S_ISLNK(info.st_mode) else None
        if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode) or link is not None):
            raise PreparationError("input contains an unsupported special file: " + str(path),
                                   "select regular files, directories, or supported relative symlinks")
        result.append((path, target, info, link))
        if stat.S_ISDIR(info.st_mode):
            for child in sorted(path.iterdir(), key=lambda item: item.name):
                relative_path(child.name, "input entry")
                visit(child, target / child.name)

    visit(source, destination)
    return result


def check_links(nodes):
    """Check source links without treating lexical normalization as resolution."""
    for source, _, _, link in nodes:
        if link is None:
            continue
        if (not link or "\\" in link or ":" in link or PurePosixPath(link).is_absolute()
                or any(ord(char) < 32 for char in link)):
            raise PreparationError("input symlink must have a relative target: " + str(source),
                                   "replace absolute links with relative links inside the selected inputs")
        try:
            source.resolve(strict=True)
            source.stat()
        except (OSError, RuntimeError):
            raise PreparationError("input symlink is broken or cyclic: " + str(source),
                                   "correct or materialize the source link before preparation")


def check_copied_links(nodes, destination_root):
    """Validate the real copied graph, including links followed before '..'."""
    declared = {destination_root.joinpath(*relative.parts): source
                for source, relative, _, link in nodes if link is None}
    for source, relative, _, link in nodes:
        if link is None:
            continue
        copied = destination_root.joinpath(*relative.parts)
        try:
            target = copied.resolve(strict=True)
            copied.stat()  # Also require the operating system to traverse this link.
        except (OSError, RuntimeError) as exc:
            raise PreparationError("copied input symlink is missing, cyclic, or not traversable: " + str(relative),
                                   "select its target and preserve the relative layout, or materialize the input") from exc
        if not within(target, destination_root):
            raise PreparationError("copied input symlink escapes the assigned input tree: " + str(relative),
                                   "keep the resolved link inside the selected copies, or materialize the input")
        if target not in declared or declared[target].resolve(strict=True) != source.resolve(strict=True):
            raise PreparationError("copied input symlink reaches an unassigned or retargeted resource: " + str(relative),
                                   "select the intended source and preserve its relationship in the copied layout")


def read_spec(path):
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise PreparationError("batch specification repeats a JSON field: " + key)
            result[key] = value
        return result

    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PreparationError("batch specification must be UTF-8 JSON", "correct the JSON file and retry") from exc


def plan_batch(spec, spec_directory, run_root):
    object_fields(spec, ("inputs", "groups"), "batch specification")
    if not isinstance(spec["inputs"], dict):
        raise PreparationError("inputs must be an object mapping input IDs to source and destination")
    if not isinstance(spec["groups"], list) or not spec["groups"]:
        raise PreparationError("groups must be a nonempty array")
    inputs = {}
    for key, item in spec["inputs"].items():
        identifier(key, "input ID")
        object_fields(item, ("source", "destination"), "input " + key)
        if not isinstance(item["source"], str) or not item["source"] or "\x00" in item["source"]:
            raise PreparationError("input source must be a nonempty filesystem path: " + key)
        source = Path(os.path.abspath(spec_directory / item["source"]))
        try:
            resolved = source.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise PreparationError("input is missing or cannot be resolved: " + key,
                                   "correct the source path; relative sources are resolved from the specification file") from exc
        if source != resolved:
            raise PreparationError("input source has a symlink component: " + key,
                                   "declare the canonical source path explicitly; internal relative links are supported")
        if source.is_dir() and within(run_root, source):
            raise PreparationError("run root is inside a selected input source: " + key,
                                   "use a source snapshot outside the run root's ancestors")
        destination = relative_path(item["destination"], "input destination")
        inputs[key] = {"source": source, "destination": destination, "nodes": inventory(source, destination)}
    groups = []
    seen = set()
    for group in spec["groups"]:
        object_fields(group, ("id", "count", "inputs", "outputs"), "group")
        name = identifier(group["id"], "group ID")
        if name in seen:
            raise PreparationError("group IDs must be unique: " + name)
        seen.add(name)
        if type(group["count"]) is not int or group["count"] < 1:
            raise PreparationError("group count must be a positive integer: " + name)
        selections = group["inputs"]
        if not isinstance(selections, list) or any(not isinstance(key, str) for key in selections):
            raise PreparationError("group inputs must be an array of input IDs: " + name)
        if len(set(selections)) != len(selections) or any(key not in inputs for key in selections):
            raise PreparationError("group inputs must name distinct declared input IDs: " + name,
                                   "available input IDs: " + (", ".join(inputs) or "none; use an empty array"))
        roots = [inputs[key]["destination"] for key in selections]
        for index, root in enumerate(roots):
            if any(within(root, other) or within(other, root) for other in roots[index + 1:]):
                raise PreparationError("selected input destinations overlap: " + name,
                                       "use distinct destinations without ancestor/descendant overlap")
        nodes = [node for key in selections for node in inputs[key]["nodes"]]
        check_links(nodes)
        if not isinstance(group["outputs"], list) or not group["outputs"]:
            raise PreparationError("group outputs must declare at least one expected relative path: " + name)
        outputs = [relative_path(value, "expected output") for value in group["outputs"]]
        if len(set(outputs)) != len(outputs):
            raise PreparationError("expected output paths must be distinct: " + name)
        groups.append({"id": name, "count": group["count"], "inputs": selections, "outputs": outputs, "nodes": nodes})
    return inputs, groups


def copy_nodes(nodes, destination_root):
    for source, relative, info, link in nodes:
        if signature(source.lstat()) != signature(info):
            raise PreparationError("input changed during preparation: " + str(source),
                                   "use stable inputs and retry with a fresh run root")
        destination = destination_root.joinpath(*relative.parts)
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if stat.S_ISDIR(info.st_mode):
            destination.mkdir(mode=0o700, exist_ok=True)
        elif link is not None:
            os.symlink(link, destination, target_is_directory=source.resolve().is_dir())
        else:
            descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as reader, destination.open("xb") as writer:
                if signature(os.fstat(reader.fileno())) != signature(info):
                    raise PreparationError("input changed during preparation: " + str(source))
                shutil.copyfileobj(reader, writer)
                if signature(os.fstat(reader.fileno())) != signature(info):
                    raise PreparationError("input changed during preparation: " + str(source))
            destination.chmod(stat.S_IMODE(info.st_mode) & 0o777)
    for source, _, info, _ in nodes:
        if signature(source.lstat()) != signature(info):
            raise PreparationError("input changed during preparation: " + str(source),
                                   "use stable inputs and retry with a fresh run root")


def write_manifest(path, manifest):
    descriptor, temporary = tempfile.mkstemp(prefix=".manifest-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(manifest, stream, separators=(",", ":"), ensure_ascii=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


def prepare_batch(run_root, spec_path):
    raw_root = Path(run_root)
    if not raw_root.is_absolute() or ".." in raw_root.parts:
        raise PreparationError("run root must be an absolute path without '..' components")
    if raw_root.parent.resolve(strict=True) != raw_root.parent:
        raise PreparationError("run root parent has a symlink component", "use the canonical parent path")
    if not raw_root.parent.is_dir():
        raise PreparationError("run root parent must be an existing directory")
    if os.path.lexists(raw_root):
        raise PreparationError("run root already exists; no files were changed",
                               "inspect the previous manifest and choose a fresh batch root; there is no overwrite or resume mode")
    spec_path = Path(spec_path).resolve(strict=True)
    spec = read_spec(spec_path)
    inputs, groups = plan_batch(spec, spec_path.parent, raw_root)
    temporary_root = Path(tempfile.gettempdir()).resolve(strict=True) / ("split-testing-" + uuid.uuid4().hex)
    if any(item["source"].is_dir() and within(temporary_root, item["source"]) for item in inputs.values()):
        raise PreparationError("system temporary storage is inside a selected input source",
                               "use a separate source snapshot or a system temporary location outside the inputs")
    try:
        raw_root.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise PreparationError("run root was claimed by another invocation; no files were changed",
                               "choose a fresh batch root") from exc
    temporary_owned = False
    participants_root = temporary_root / "participants"
    archive = raw_root / "archive"
    manifest_path = archive / "manifest.json"
    manifest = {
        "schema_version": 1,
        "preparation_status": "preparing",
        "run_root": str(raw_root),
        "archive": str(archive),
        "temporary_root": str(temporary_root),
        "temporary_root_created": False,
        "specification": str(spec_path),
        "batch": spec,
        "boundaries": {
            "preparation_enforced": ["fresh_owned_run_root", "selected_input_copies", "validated_relative_paths", "validated_copied_symlink_targets"],
            "host_enforced": [],
            "requires_agent_compliance": ["read_only_assigned_inputs", "write_only_assigned_outputs", "no_access_to_sibling_workspaces_or_controller_archive"],
            "not_verified": ["fresh_context", "host_inheritance", "ignored_context_location"],
        },
        "participants": [],
    }
    try:
        archive.mkdir(mode=0o700)
        write_manifest(manifest_path, manifest)
        temporary_root.mkdir(mode=0o700)
        temporary_owned = True
        manifest["temporary_root_created"] = True
        write_manifest(manifest_path, manifest)
        participants_root.mkdir(mode=0o700)
        (archive / "retained").mkdir(mode=0o700)
        for group in groups:
            for _ in range(group["count"]):
                workspace = Path(tempfile.mkdtemp(prefix="p-", dir=participants_root))
                input_root = workspace / "inputs"
                output_root = workspace / "outputs"
                input_root.mkdir(mode=0o700)
                output_root.mkdir(mode=0o700)
                retained = archive / "retained" / workspace.name
                retained.mkdir(mode=0o700)
                participant = {
                    "id": workspace.name, "group": group["id"], "host_agent_id": None,
                    "workspace": str(workspace),
                    "inputs": {key: str(input_root.joinpath(*inputs[key]["destination"].parts)) for key in group["inputs"]},
                    "output_root": str(output_root),
                    "expected_outputs": [str(output_root.joinpath(*path.parts)) for path in group["outputs"]],
                    "retained_outputs": str(retained), "prepared": False,
                }
                manifest["participants"].append(participant)
                write_manifest(manifest_path, manifest)
                copy_nodes(group["nodes"], input_root)
                check_copied_links(group["nodes"], input_root)
                participant["prepared"] = True
        manifest["preparation_status"] = "ready"
        write_manifest(manifest_path, manifest)
    except BaseException as exc:
        interrupted = isinstance(exc, (KeyboardInterrupt, InterruptedError))
        try:
            committed = json.loads(manifest_path.read_text(encoding="utf-8")).get("preparation_status") == "ready"
        except (OSError, ValueError):
            committed = False
        if committed:
            raise PreparationError("batch is ready, but result delivery was interrupted",
                                   "recover the prepared participant locations from " + str(manifest_path),
                                   130 if interrupted else 2) from exc
        manifest["preparation_status"] = "interrupted" if interrupted else "failed"
        manifest["failure"] = type(exc).__name__
        manifest["partial_workspaces_removed"] = False
        try:
            if temporary_owned:
                shutil.rmtree(temporary_root)
                manifest["partial_workspaces_removed"] = True
        except OSError as cleanup_error:
            manifest["cleanup_failure"] = type(cleanup_error).__name__
        try:
            if archive.is_dir():
                write_manifest(manifest_path, manifest)
        except OSError:
            pass  # A missing/non-ready manifest still cannot authorize dispatch.
        detail = str(exc) if isinstance(exc, PreparationError) else type(exc).__name__
        raise PreparationError("preparation {}: {}".format(manifest["preparation_status"], detail),
                               "inspect {}; use a fresh batch root after correcting the failure".format(manifest_path),
                               130 if interrupted else 2) from exc
    return {"preparation_status": "ready", "run_root": str(raw_root), "archive": str(archive),
            "temporary_root": str(temporary_root),
            "manifest": str(manifest_path), "participants": manifest["participants"]}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise PreparationError(message, "use --help for the accepted command options")


def main(argv=None):
    parser = Parser(description="Create one fresh participant batch from a JSON specification. Python 3; standard library only.",
                    epilog="The controller supplies an ignored local-context parent, dispatches agents, retains outputs, and cleans up. No sandbox is created. See references/workspaces.md for the JSON schema.")
    parser.add_argument("--run-root", required=True, help="new absolute controller batch directory; its parent must exist")
    parser.add_argument("--spec", required=True, help="JSON batch file; relative input sources resolve beside this file")
    parser.add_argument("--summary-only", action="store_true", help="omit participant details from stdout; keep them in the manifest")
    try:
        args = parser.parse_args(argv)
        result = prepare_batch(args.run_root, args.spec)
        if args.summary_only:
            result["participant_count"] = len(result.pop("participants"))
        print(json.dumps(result, separators=(",", ":"), ensure_ascii=True))
        return 0
    except PreparationError as exc:
        print("error: " + str(exc), file=sys.stderr)
        print("hint: " + exc.hint, file=sys.stderr)
        return exc.code
    except (KeyboardInterrupt, InterruptedError):
        print("error: preparation interrupted before completion", file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError) as exc:
        detail = exc.strerror if isinstance(exc, OSError) else type(exc).__name__
        print("error: cannot prepare batch: " + str(detail), file=sys.stderr)
        print("hint: check the specification, existing parent, paths and filesystem permissions; use a fresh batch root", file=sys.stderr)
        return 2


if __name__ == "__main__":
    def terminate(signum, frame):
        raise InterruptedError("received termination signal")

    signal.signal(signal.SIGTERM, terminate)
    sys.exit(main())
