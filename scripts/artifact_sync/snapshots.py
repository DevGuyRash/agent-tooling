"""Read declared source trees from a worktree, Git index, or committed revision."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from .model import ArtifactError, Item, digest, matches, path_name


def git(root: Path, *args, data: bytes | None = None, env=None) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args], input=data, capture_output=True,
                            env=env, timeout=120)
    if result.returncode:
        message = result.stderr.decode("utf-8", "replace").strip().splitlines()
        raise ArtifactError(message[0] if message else "Git operation failed")
    return result.stdout


def repository(path: Path) -> Path:
    return Path(git(path.resolve(), "rev-parse", "--show-toplevel").decode().strip()).resolve()


def index_path(root: Path) -> Path:
    chosen = os.environ.get("GIT_INDEX_FILE")
    if chosen:
        return Path(os.path.abspath(root / chosen))
    return Path(git(root, "rev-parse", "--path-format=absolute", "--git-path", "index").decode().strip())


def primary_index_path(root: Path) -> Path:
    env = os.environ.copy()
    env.pop("GIT_INDEX_FILE", None)
    return Path(git(root, "rev-parse", "--path-format=absolute", "--git-path", "index", env=env).decode().strip())


def read_item(path: Path) -> Item | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if path.is_symlink():
        return Item(os.fsencode(os.readlink(path)), "120000")
    if not path.is_file():
        raise ArtifactError(f"expected a regular file: {path}")
    return Item(path.read_bytes(), "100755" if info.st_mode & 0o111 else "100644")


def safe_destination(root: Path, relative: str) -> Path:
    path_name(relative)
    result = root / relative
    for parent in result.parents:
        if parent == root:
            break
        if parent.is_symlink():
            raise ArtifactError(f"destination traverses a symlink: {relative}")
    return result


def write_item(root: Path, name: str, item: Item | None):
    destination = safe_destination(root, name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if item is None:
        if destination.is_dir() and not destination.is_symlink():
            raise ArtifactError(f"cannot remove a directory as a file: {name}")
        destination.unlink(missing_ok=True)
        return
    fd, temporary = tempfile.mkstemp(prefix=".artifact-", dir=destination.parent)
    try:
        if item.mode == "120000":
            os.close(fd)
            os.unlink(temporary)
            os.symlink(os.fsdecode(item.data), temporary)
        else:
            with os.fdopen(fd, "wb") as stream:
                stream.write(item.data)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o755 if item.mode == "100755" else 0o644)
        os.replace(temporary, destination)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


class Snapshot:
    def __init__(self, root: Path, source: str = "worktree"):
        self.root = root
        self.source = source
        self.cache: dict[str, Item | None] = {}
        self.entries: dict[str, tuple[str, str]] = {}
        self.index_file = index_path(root)
        self.index_bytes = self.index_file.read_bytes() if self.index_file.exists() else None
        self.env = os.environ.copy()
        self.env["GIT_INDEX_FILE"] = str(self.index_file)
        if source == "worktree":
            names = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
            self.names = set(os.fsdecode(n) for n in names.split(b"\0") if n)
        elif source == "index":
            raw = git(root, "ls-files", "--stage", "-z", env=self.env)
            for line in raw.split(b"\0"):
                if not line:
                    continue
                metadata, raw_name = line.split(b"\t", 1)
                mode, oid, stage = metadata.decode().split()
                if stage != "0":
                    raise ArtifactError("the index contains unresolved merges", "resolve them before generating artifacts")
                self.entries[os.fsdecode(raw_name)] = (mode, oid)
            self.names = set(self.entries)
            after = self.index_file.read_bytes() if self.index_file.exists() else None
            if after != self.index_bytes:
                raise ArtifactError("the Git index changed while it was being read", "retry with a stable index")
        elif source.startswith("commit:"):
            revision = source.split(":", 1)[1]
            oid = git(root, "rev-parse", "--verify", "--end-of-options", revision + "^{commit}").decode().strip()
            raw = git(root, "ls-tree", "-rz", "--full-tree", oid)
            for line in raw.split(b"\0"):
                if not line:
                    continue
                metadata, raw_name = line.split(b"\t", 1)
                mode, _kind, blob = metadata.decode().split()
                self.entries[os.fsdecode(raw_name)] = (mode, blob)
            self.names = set(self.entries)
            self.source = "commit:" + oid
        else:
            raise ArtifactError("source must be worktree, index, or commit:<git-object>")

    def get(self, name: str) -> Item | None:
        if name not in self.cache:
            if self.source == "worktree":
                self.cache[name] = read_item(safe_destination(self.root, name))
            elif name not in self.entries:
                self.cache[name] = None
            else:
                mode, oid = self.entries[name]
                if mode not in {"100644", "100755", "120000"}:
                    raise ArtifactError(f"unsupported Git input mode {mode}: {name}", "materialize the required source files explicitly")
                self.cache[name] = Item(git(self.root, "cat-file", "blob", oid), mode)
        return self.cache[name]

    def files(self, patterns, optional=(), exclude=(), overlay=None) -> dict[str, Item]:
        overlay = overlay or {}
        names = self.names | set(overlay)
        result = {}
        for pattern in (*patterns, *optional):
            selected = [name for name in names if matches(name, pattern)
                        and not any(matches(name, p) for p in exclude)]
            found = False
            for name in sorted(selected):
                item = overlay.get(name) if name in overlay else self.get(name)
                if item is not None:
                    result[name] = item
                    found = True
            if not found and pattern not in optional:
                raise ArtifactError(f"declared input has no files: {pattern}", "include the input in the selected source snapshot")
        return result

    def destination_files(self, directory: str) -> dict[str, Item]:
        if self.source != "worktree":
            return self.files((), (directory,))
        root = safe_destination(self.root, directory)
        if root.is_symlink():
            raise ArtifactError(f"output directory is a symlink: {directory}")
        if not root.exists():
            return {}
        if not root.is_dir():
            raise ArtifactError(f"output directory is occupied by a file: {directory}")
        return {p.relative_to(self.root).as_posix(): self.get(p.relative_to(self.root).as_posix())
                for p in sorted(root.rglob("*")) if p.is_file() or p.is_symlink()}


def materialize(root: Path, entries: dict[str, Item]):
    for name, item in entries.items():
        write_item(root, name, item)
    for name, item in entries.items():
        if item.mode == "120000":
            try:
                resolved = (root / name).resolve(strict=True)
                resolved.relative_to(root)
            except (OSError, RuntimeError, ValueError) as exc:
                raise ArtifactError(f"input symlink escapes or reaches an undeclared file: {name}") from exc
