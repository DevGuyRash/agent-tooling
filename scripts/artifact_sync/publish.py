"""Recoverable publication of owned files and a selected Git index."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

from .model import ArtifactError, Item, digest, json_bytes, path_name
from .snapshots import git, primary_index_path, read_item, safe_destination, write_item

MARKER = "artifact-publication-v1"


def git_directory(root):
    return Path(git(root, "rev-parse", "--absolute-git-dir").decode().strip())


def alive(pid):
    if os.name == "nt":
        # os.kill(pid, 0) terminates processes on Windows. Query, never signal.
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() != 87  # Only a nonexistent PID is stale.
        try:
            code = wintypes.DWORD()
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


@contextmanager
def publication_lock(root):
    directory = git_directory(root)
    lock = directory / "artifact-sync.lock"
    deadline = time.monotonic() + 15
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError:
            if lock.is_symlink():
                raise ArtifactError("artifact lock is a symlink")
            try:
                content = lock.read_bytes()
                owner = json.loads(content)
                if owner.get("kind") == MARKER and type(owner.get("pid")) is int and not alive(owner["pid"]):
                    if lock.read_bytes() == content:
                        lock.unlink()
                        continue
            except (OSError, ValueError):
                pass
            if time.monotonic() >= deadline:
                raise ArtifactError("another artifact publication holds the lock", "retry after that process finishes")
            time.sleep(.05)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(json_bytes({"kind": MARKER, "pid": os.getpid()}))
            stream.flush()
            os.fsync(stream.fileno())
        recover(root)
        yield
    finally:
        lock.unlink(missing_ok=True)


def put_meta(directory, meta):
    write_item(directory, "transaction.json", Item(json_bytes(meta)))


def saved_item(directory, record, side):
    value = record[side]
    if value is None:
        return None
    data = (directory / value["file"]).read_bytes()
    if digest(data) != value["sha256"]:
        raise ArtifactError("publication recovery data is damaged", f"inspect {directory} before retrying")
    return Item(data, value["mode"])


def same(left, right):
    return left is None and right is None or left is not None and left.same(right)


def unlink_owned_lock(path, identity):
    if path is None or identity is None:
        return
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if not path.is_symlink() and (info.st_dev, info.st_ino) == identity:
        path.unlink()


def recover(root):
    directory = git_directory(root) / "artifact-publication"
    if not directory.exists():
        return
    if directory.is_symlink():
        raise ArtifactError("publication recovery directory is a symlink")
    try:
        meta = json.loads((directory / "transaction.json").read_bytes())
        if meta["kind"] != MARKER or meta["root"] != str(root):
            raise ValueError()
        for record in meta["files"]:
            path_name(record["path"])
        index = Path(meta["index"]) if meta["index"] else None
        committed = meta["phase"] == "complete"
        if index:
            current = index.read_bytes() if index.exists() else None
            identity = digest(current) if current is not None else None
            if identity == meta["new_index"]:
                committed = True
            elif identity != meta["old_index"]:
                raise ArtifactError("the index changed after an interrupted publication",
                                    f"preserve and inspect recovery data in {directory}")
            index_lock = Path(str(index) + ".lock")
            if index_lock.exists():
                info = index_lock.stat()
                identity = [info.st_dev, info.st_ino]
                if identity != meta["index_lock_identity"] or alive(meta["pid"]):
                    raise ArtifactError("an active or unrelated Git index lock prevents recovery")
                index_lock.unlink()
        for record in meta["files"]:
            current = read_item(safe_destination(root, record["path"]))
            before = saved_item(directory, record, "before")
            after = saved_item(directory, record, "after")
            if not (same(current, before) or same(current, after)):
                raise ArtifactError(f"output changed after interruption: {record['path']}",
                                    f"preserve manual edits and inspect {directory}")
        for record in meta["files"]:
            target = saved_item(directory, record, "after" if committed else "before")
            write_item(root, record["path"], target)
        temporary_index = Path(meta["temporary_index"]) if meta.get("temporary_index") else None
        if temporary_index and temporary_index.exists():
            if (index is None or temporary_index.parent != index.parent
                    or not temporary_index.name.startswith("artifact-index-")
                    or temporary_index.is_symlink() or digest(temporary_index.read_bytes()) != meta["new_index"]):
                raise ArtifactError("temporary index recovery identity differs", f"inspect {directory}")
            temporary_index.unlink()
        shutil.rmtree(directory)
    except ArtifactError:
        raise
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise ArtifactError("incomplete publication recovery data",
                            f"preserve and inspect {directory}") from exc


def publish(root, changes: dict[str, Item | None], expected: dict[str, Item | None], *,
            index=None, original_index: bytes | None = None, guard=lambda: None):
    if not changes:
        guard()
        return
    with publication_lock(root):
        guard()
        if index:
            primary = primary_index_path(root)
            if index != primary and Path(str(primary) + ".lock").exists():
                raise ArtifactError("Git is retaining a second locked index during artifact generation",
                                    "finish the other Git operation; for commit --only/--include, stage the desired paths and use a regular commit")
        for name in changes:
            current = read_item(safe_destination(root, name))
            if not same(current, expected[name]):
                raise ArtifactError(f"destination changed while preparing: {name}",
                                    "preserve the concurrent edit and rerun")
        lock_path = Path(str(index) + ".lock") if index else None
        fd = None
        owned_index_lock = None
        directory = git_directory(root) / "artifact-publication"
        temporary_index = None
        try:
            if index:
                if index.is_symlink():
                    raise ArtifactError("the selected index is a symlink")
                try:
                    fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    info = os.fstat(fd)
                    owned_index_lock = (info.st_dev, info.st_ino)
                except FileExistsError as exc:
                    raise ArtifactError("the selected Git index is locked", "finish the other Git operation and retry") from exc
                now = index.read_bytes() if index.exists() else None
                if now != original_index:
                    raise ArtifactError("the Git index changed during preparation", "retry; unrelated staging is preserved")
                handle, filename = tempfile.mkstemp(prefix="artifact-index-", dir=index.parent)
                os.close(handle)
                temporary_index = Path(filename)
                env = os.environ.copy()
                env["GIT_INDEX_FILE"] = str(temporary_index)
                if original_index is None:
                    temporary_index.unlink()
                    git(root, "read-tree", "--empty", env=env)
                else:
                    temporary_index.write_bytes(original_index)
                    git(root, "update-index", "--no-split-index", env=env)
                lines = []
                for name, item in sorted(changes.items()):
                    if item is None:
                        lines.append(b"0 " + b"0" * 40 + b"\t" + os.fsencode(name) + b"\0")
                    else:
                        oid = git(root, "hash-object", "-w", "--stdin", data=item.data).strip()
                        lines.append(item.mode.encode() + b" " + oid + b"\t" + os.fsencode(name) + b"\0")
                git(root, "update-index", "-z", "--index-info", data=b"".join(lines), env=env)
                new_index_bytes = temporary_index.read_bytes()
            else:
                new_index_bytes = None
            directory.mkdir(mode=0o700)
            meta = {
                "kind": MARKER, "root": str(root), "pid": os.getpid(), "phase": "preparing",
                "index": str(index) if index else None,
                "old_index": digest(original_index) if original_index is not None else None,
                "new_index": digest(new_index_bytes) if new_index_bytes is not None else None,
                "temporary_index": str(temporary_index) if temporary_index else None,
                "index_lock_identity": [os.fstat(fd).st_dev, os.fstat(fd).st_ino] if fd is not None else None,
                "files": [],
            }
            put_meta(directory, meta)
            for number, (name, after) in enumerate(sorted(changes.items())):
                record = {"path": name}
                for side, item in (("before", expected[name]), ("after", after)):
                    if item is None:
                        record[side] = None
                    else:
                        filename = f"{number}-{side}"
                        (directory / filename).write_bytes(item.data)
                        record[side] = {"file": filename, **item.identity}
                meta["files"].append(record)
            meta["phase"] = "prepared"
            put_meta(directory, meta)
            for name, item in sorted(changes.items()):
                if not same(read_item(safe_destination(root, name)), expected[name]):
                    raise ArtifactError(f"destination changed during publication: {name}")
                write_item(root, name, item)
            if fd is not None:
                handle = fd
                fd = None
                with os.fdopen(handle, "wb") as stream:
                    stream.write(new_index_bytes)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(lock_path, index)
                owned_index_lock = None
            meta["phase"] = "complete"
            put_meta(directory, meta)
            shutil.rmtree(directory)
        except BaseException:
            if fd is not None:
                os.close(fd)
                fd = None
            released_identity, owned_index_lock = owned_index_lock, None
            unlink_owned_lock(lock_path, released_identity)
            if directory.exists() and (directory / "transaction.json").exists():
                # The index identifies the committed side after an interruption.
                recover(root)
            elif directory.exists():
                shutil.rmtree(directory)
            raise
        finally:
            if fd is not None:
                os.close(fd)
            unlink_owned_lock(lock_path, owned_index_lock)
            if temporary_index:
                temporary_index.unlink(missing_ok=True)
