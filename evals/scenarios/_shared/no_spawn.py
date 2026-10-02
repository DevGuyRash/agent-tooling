"""Check helpers for scenarios where a compiled program must do its own work rather than start another language's
interpreter, adding to _shared/no_interpreter.py (imported here as ni):

- seal(argv) and execute_sealed(...): ni.minimal's root made read-only throughout (/, /tmp, /dev) and run with
  memfd_create and execveat refused, so the only programs that can start in it are the ones already there: the
  program under test and the C runtime it loads. ni.minimal alone leaves /tmp writable, where a program that
  carries an interpreter (its bytes compiled in, a frozen bundle) could write it out and run it; here it cannot,
  on disk or in memory. For a program that legitimately needs a temporary file (a JVM's port of a script that
  calls mktemp), seal(argv, tmp_size=N) leaves a writable /tmp of N bytes, and execute_sealed(..., no_process=True)
  then refuses what the memfd and execveat filter leaves, creating a process at all (fork, vfork, and clone without
  CLONE_THREAD, with clone3 answered ENOSYS so the C library falls back to clone): nothing written there can run.
  The two go together, and execute_sealed refuses a writable /tmp without the filter.
- the recorded root (recorder_dir, interpreter_files, recorded, starts, recorder_works): the ordinary confined
  root with every interpreter and shell on its PATH replaced by a recorder that notes its own start and exits 127,
  each case run under a supervisor that waits, at most SETTLE_MS, for whatever the program left running. The
  minimal root shows a program works without an interpreter; this shows it leaves one alone when one is there, so
  a program that runs a helper through python3 whenever python3 exists, and falls back to its own code where it
  does not, shows here. It sees process starts only: Python run inside the program through the host's libpython
  starts nothing, and python_embedding is the static sign of that. The recorder and supervisor run on a copy of
  the host's python3 at REC_BIN, a path no program looks in, so replacing the real one does not stop them.
- shared case files (load, materialize): hidden cases whose files are stored once in cases.json, by content, and
  named per case.
- the shipped source, for static checks: go_package_files (the Go files `go list -deps` says a package is built
  from), cargo_dep_files (the files cargo's dep-info names for a built binary), rust_shipped_sources (that Rust,
  or every .rs outside tests/, benches/, and examples/ when the build left no dep-info, with #[cfg(test)] and
  #[test] items left out), rust_test_spans (where those items are in a file's own text, for a check that reads
  positions there), and python_embedding (shipped files that name the host's Python library or its C API).

Everything runs through bubblewrap; a missing python3 on the host (needed only by the recorded root) raises
ni.Unavailable, which makes the run invalid rather than failed.
"""
import base64
import json
import os
import platform
import re
import shutil
import stat
import struct
import subprocess
from pathlib import Path

import no_interpreter as ni

REC_LOG = "/run/trial-rec"        # in the recorded root: where the recorder notes each start (writable)
REC_BIN = "/run/trial-recorder"   # in the recorded root: the recorder, its interpreter, and the supervisor
SETTLE_MS = 10_000                # the longest the supervisor waits for what a program left running

# ---------------------------------------------------------------- the sealed minimal root

# (AUDIT_ARCH value, syscall numbers of memfd_create and execveat, x32 syscall bit or None) by machine.
_SECCOMP_ARCH = {
    "x86_64": (0xC000003E, (319, 322), 0x40000000),
    "aarch64": (0xC00000B7, (279, 281), None),
}


def _seccomp_program():
    """A classic-BPF seccomp filter (bubblewrap's --seccomp format) that refuses memfd_create and execveat with
    EPERM, and any syscall made through another ABI than the machine's own; None on an unlisted machine."""
    arch = _SECCOMP_ARCH.get(platform.machine())
    if arch is None:
        return None
    audit, numbers, x32 = arch
    ld, jeq, jge, ret = 0x20, 0x15, 0x35, 0x06
    allow, refuse = 0x7FFF0000, 0x00050000 | 1   # SECCOMP_RET_ALLOW, SECCOMP_RET_ERRNO | EPERM
    checks = ([(jge, x32)] if x32 else []) + [(jeq, n) for n in numbers]
    refuse_at = 3 + len(checks) + 1   # index of the final "return EPERM"
    prog = [(ld, 0, 0, 4), (jeq, 0, refuse_at - 2, audit), (ld, 0, 0, 0)]
    for code, k in checks:
        prog.append((code, refuse_at - len(prog) - 1, 0, k))
    prog += [(ret, 0, 0, allow), (ret, 0, 0, refuse)]
    return b"".join(struct.pack("=HBBI", *ins) for ins in prog)


# (AUDIT_ARCH value, {syscall: errno} refused outright, clone, clone3, x32 syscall bit or None) by machine.
_PROCESS_SYSCALLS = {
    "x86_64": (0xC000003E, {319: 1, 322: 1, 57: 1, 58: 1}, 56, 435, 0x40000000),   # memfd_create, execveat, fork, vfork
    "aarch64": (0xC00000B7, {279: 1, 281: 1}, 220, 435, None),                      # memfd_create, execveat
}
CLONE_THREAD = 0x00010000
ENOSYS = 38


def _no_process_program():
    """A classic-BPF seccomp filter (bubblewrap's --seccomp format) under which no process can be created:
    memfd_create, execveat, fork, vfork, clone without CLONE_THREAD, and any other ABI's syscalls refused with
    EPERM, and clone3 answered ENOSYS, which makes the C library create threads with clone. None on an unlisted
    machine."""
    spec = _PROCESS_SYSCALLS.get(platform.machine())
    if spec is None:
        return None
    audit, refused, clone, clone3, x32 = spec
    LD, JEQ, JGE, JSET, RET = 0x20, 0x15, 0x35, 0x45, 0x06
    ALLOW, ERRNO = 0x7FFF0000, 0x00050000
    # (code, k, true label, false label) with labels resolved below; None falls through.
    prog = [("ld", 4), ("jeq", audit, None, "eperm"), ("ld", 0)]
    if x32:
        prog.append(("jge", x32, "eperm", None))
    prog += [("jeq", nr, "eperm", None) for nr in refused]
    prog += [("jeq", clone3, "enosys", None), ("jeq", clone, None, "allow"), ("ld", 16),
             ("jset", CLONE_THREAD, "allow", "eperm"),
             ("label", "allow"), ("ret", ALLOW), ("label", "eperm"), ("ret", ERRNO | 1),
             ("label", "enosys"), ("ret", ERRNO | ENOSYS)]
    at, n = {}, 0
    for ins in prog:
        if ins[0] == "label":
            at[ins[1]] = n
        else:
            n += 1
    out, n = [], 0
    for ins in prog:
        if ins[0] == "label":
            continue
        n += 1
        if ins[0] == "ld":
            out.append((LD, 0, 0, ins[1]))
        elif ins[0] == "ret":
            out.append((RET, 0, 0, ins[1]))
        else:
            code = {"jeq": JEQ, "jge": JGE, "jset": JSET}[ins[0]]
            jt = at[ins[2]] - n if ins[2] else 0
            jf = at[ins[3]] - n if ins[3] else 0
            out.append((code, jt, jf, ins[1]))
    return b"".join(struct.pack("=HBBI", *ins) for ins in out)


def seal(argv, tmp_size=None):
    """ni.minimal's argv (ending in --chdir DIR --) with the whole root made read-only: no file can be written
    anywhere in it, so nothing can be unpacked and run. With tmp_size (bytes), /tmp stays writable as a tmpfs of
    that size, which is safe only under execute_sealed(no_process=True); on a machine whose process filter is not
    known, /tmp is read-only as without it."""
    if argv[-3] != "--chdir" or argv[-1] != "--":
        raise RuntimeError("unexpected minimal-root layout")
    if tmp_size is None or _no_process_program() is None:
        return argv[:-3] + ["--remount-ro", "/tmp", "--remount-ro", "/dev", "--remount-ro", "/"] + argv[-3:]
    t = argv.index("--tmpfs")
    if argv[t + 1] != "/tmp":
        raise RuntimeError("unexpected minimal-root layout")
    argv = argv[:t] + ["--size", str(tmp_size)] + argv[t:]
    return argv[:-3] + ["--remount-ro", "/dev", "--remount-ro", "/"] + argv[-3:]


def execute_sealed(argv, env=None, stdin=b"", timeout=60, no_process=False):
    """ni.execute for an argv built by seal(), with the seccomp filter handed to bubblewrap: (exit status or None
    on timeout, stdout bytes, stderr bytes). no_process swaps the filter for the one under which no process can be
    created (see _no_process_program); an argv with a writable /tmp (seal's tmp_size) needs it."""
    if not no_process and "/tmp" not in {a for p, a in zip(argv, argv[1:]) if p == "--remount-ro"}:
        raise RuntimeError("a sealed root with a writable /tmp must run with no_process=True")
    program = (_no_process_program() if no_process else None) or _seccomp_program()
    if program is None:
        return ni.execute(argv, env=env, stdin=stdin, timeout=timeout)
    r, w = os.pipe()
    try:
        os.write(w, program)
        os.close(w)
        w = None
        try:
            p = subprocess.run([argv[0], "--seccomp", str(r), *argv[1:]], env=env if env is not None else {},
                               input=stdin, capture_output=True, timeout=timeout, pass_fds=(r,))
            return p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired:
            return None, b"", b"time limit reached"
    finally:
        os.close(r)
        if w is not None:
            os.close(w)


def sealed_filters(no_process=False):
    """What the sealed root refuses beyond writing, for the record: 'memfd_create,execveat' or 'none'; with
    no_process, the process-creating calls too (and 'tmp-read-only' where the filter is not known, as seal then
    leaves /tmp read-only)."""
    if no_process:
        return ("memfd_create,execveat,fork,vfork,clone-without-thread,clone3" if _no_process_program()
                else sealed_filters() + ",tmp-read-only")
    return "memfd_create,execveat" if _seccomp_program() else "none"


# ---------------------------------------------------------------- the recorded root

_RECORDER = f"""#!{REC_BIN}/python -IS
import json, os, sys
name = os.path.basename(sys.argv[0]) or "?"
try:
    with open("{REC_LOG}/starts", "a", encoding="utf-8") as fh:
        fh.write(json.dumps([name, *sys.argv[1:]]) + "\\n")
except OSError:
    pass
sys.stderr.write(name + ": start recorded by the check, not run\\n")
sys.exit(127)
"""

_SETTLE = """import os, subprocess, sys, time
limit = int(sys.argv[1]) / 1000
try:
    child = subprocess.Popen(sys.argv[2:])
except OSError as exc:
    sys.stderr.write(f"settle: {exc}\\n")
    sys.exit(127)
status = child.wait()
status = 128 - status if status < 0 else status
deadline = time.monotonic() + limit


def others_left():
    me = os.getpid()
    for name in os.listdir("/proc"):
        if not name.isdigit() or int(name) in (1, me):
            continue
        try:
            with open(f"/proc/{name}/stat", encoding="utf-8", errors="replace") as fh:
                stat = fh.read()
        except OSError:
            continue
        if stat[stat.rindex(")") + 2] not in "ZX":
            return True
    return False


while others_left() and time.monotonic() < deadline:
    time.sleep(0.01)
sys.exit(status)
"""


def host_python():
    """The host's python3 executable, resolved through links, from the PATH the ordinary root has."""
    found = shutil.which("python3", path=ni.HOST_PATH)
    if not found:
        raise ni.Unavailable(f"the recorded root needs python3 on {ni.HOST_PATH}")
    return os.path.realpath(found)


def recorder_dir(base):
    """base/recorder: a copy of the host's python3, the recorder, and the supervisor, bound read-only at REC_BIN.
    Make it before anything of the agent's runs, and keep it read-only (`readonly` in ni.cargo or ni.go) while
    anything does."""
    d = Path(base) / "recorder"
    d.mkdir()
    shutil.copyfile(host_python(), d / "python")
    (d / "recorder").write_text(_RECORDER)
    (d / "settle.py").write_text(_SETTLE)
    for name in ("python", "recorder"):
        os.chmod(d / name, 0o755)
    return d


def interpreter_files(path=ni.HOST_PATH, keep=()):
    """Real files of the interpreters and shells a program in the ordinary root can start by name or by path: each
    executable in path's directories whose name ni.INTERPRETER matches or contains "python" (vtkpython and other
    programs that carry the host's libpython), outside the home, except the real files of `keep`. Links to one (sh
    to bash, python3 to python3.14) reach the recorder bound at its real file."""
    kept = {os.path.realpath(k) for k in keep}
    found = {}
    for d in dict.fromkeys(os.path.realpath(d) for d in path.split(":") if os.path.isdir(d)):
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        for name in names:
            real = os.path.realpath(os.path.join(d, name))
            if ((ni.INTERPRETER.fullmatch(name) or "python" in name) and real not in kept and os.path.isfile(real)
                    and os.access(real, os.X_OK) and not Path(real).is_relative_to(Path.home())):
                found[real] = None
    return list(found)


def recorded(confined_argv, rec_dir, log_dir, targets, program_argv, settle_ms=SETTLE_MS):
    """An ni.confined argv (ending in --chdir DIR --) turned into the recorded root: the recorder bound over each
    of targets, rec_dir read-only at REC_BIN, log_dir writable at REC_LOG, and program_argv run under the
    supervisor."""
    if confined_argv[-3] != "--chdir" or confined_argv[-1] != "--":
        raise RuntimeError("unexpected confined-root layout")
    binds = ["--bind", str(log_dir), REC_LOG, "--ro-bind", str(rec_dir), REC_BIN]
    for target in targets:
        binds += ["--ro-bind", str(Path(rec_dir) / "recorder"), target]
    return (confined_argv[:-3] + binds + confined_argv[-3:]
            + [f"{REC_BIN}/python", "-I", "-S", f"{REC_BIN}/settle.py", str(settle_ms), *program_argv])


def starts(log_dir):
    """[[name, args...], ...] the recorder noted in log_dir."""
    out = []
    path = Path(log_dir) / "starts"
    for line in path.read_text(errors="replace").splitlines() if path.is_file() else []:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, list) and rec and all(isinstance(x, str) for x in rec):
            out.append(rec)
    return out


def recorder_works(base, rec_dir, targets, hide=(), mount=ni.MOUNT):
    """True when a start of every target, by its path, is noted in the recorded root on this host."""
    log = Path(base) / "rec-probe"
    log.mkdir()
    try:
        code = "import subprocess, sys\nfor p in sys.argv[1:]:\n    subprocess.run([p, '-c', 'true'])\n"
        argv = recorded(ni.confined(base, mount, writable=False, hide=hide), rec_dir, log, targets,
                        ["-c", code, *targets])
        # run the probe directly on the recorder's python rather than under the supervisor
        i = argv.index(f"{REC_BIN}/settle.py")
        argv = argv[:i] + argv[i + 2:]
        ni.execute(argv, env=ni.case_env(ni.HOST_PATH), timeout=120)
        return len(starts(log)) == len(targets)
    finally:
        ni.remove_tree(log)


# ---------------------------------------------------------------- placing and running the built program

def minimal_at(binary, data_dir, data_at, chdir, libs):
    """ni.minimal with data_dir bound read-only at data_at instead of /work, so file arguments are the same
    absolute paths there as in the ordinary root."""
    argv = ni.minimal(binary, data_dir, chdir=chdir, libs=libs)
    i = argv.index(str(data_dir))
    if argv[i - 1] != "--ro-bind" or argv[i + 1] != "/work":
        raise RuntimeError("unexpected minimal-root layout")
    argv[i + 1] = data_at
    return argv


def remove_path(path):
    """Remove a file, link, or directory, never following a link."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return
    if stat.S_ISDIR(st.st_mode):
        ni.remove_tree(path)
    else:
        os.unlink(path)


def put_binary(code, rel, src):
    """Copy the built program to code/rel (where the project's own build leaves it), replacing whatever the
    agent's tree has on that path; a file or link on the way is removed, never followed."""
    parent = Path(code)
    for part in Path(rel).parts[:-1]:
        parent = parent / part
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            remove_path(parent)
    if not ni.place(code, rel, src):
        raise RuntimeError(f"could not place the program at {rel}")
    os.chmod(Path(code) / rel, 0o755)


# ---------------------------------------------------------------- shared case files

def load(path):
    """(cases, {file key: base64}) from a cases.json whose cases name their files by key."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return doc["cases"], doc["files"]


def materialize(cases, files, root):
    """Write each case's files into root/NNN/, the case's own directory."""
    for i, case in enumerate(cases):
        work = Path(root) / f"{i:03d}"
        work.mkdir(parents=True)
        for name, key in case.get("files", {}).items():
            target = work / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(base64.b64decode(files[key]))


# ---------------------------------------------------------------- the shipped source

_GO_LIST = "{{if not .Standard}}{{.Dir}}{{range .GoFiles}}\t{{.}}{{end}}{{range .CgoFiles}}\t{{.}}{{end}}{{end}}"


def go_package_files(base, code_at, package, readonly=(), hide=()):
    """Paths, relative to the code at code_at (a path inside base's mount), of the Go files `go build package`
    compiles from that tree (tests, files other build constraints leave out, and packages only tests import are not
    among them); None when go list fails. go list reads the files and runs nothing of them."""
    rc, out, _ = ni.go(base, code_at, ["list", "-deps", "-f", _GO_LIST, package], readonly=readonly, hide=hide,
                       timeout=300)
    if rc != 0:
        return None
    files = []
    for line in out.decode("utf-8", "replace").splitlines():
        directory, *names = line.split("\t")
        if directory == code_at or directory.startswith(code_at + "/"):
            rel = directory[len(code_at):].strip("/")
            files += [f"{rel}/{n}" if rel else n for n in names]
    return files


def cargo_dep_files(dep_file, code_at, base, project="."):
    """Paths, relative to the code at code_at, of the files cargo's dep-info (target/PROFILE/NAME.d) names for the
    binary it built: the sources of every crate in the tree that went into it and the files they compile in. A
    relative path (a dep-info-basedir setting) is taken from the project's directory. None without dep-info, or
    when the file is a link or lies outside base (the check's scratch directory) once links on the way resolve."""
    try:
        if Path(dep_file).is_symlink() or not Path(dep_file).resolve().is_relative_to(Path(base).resolve()):
            return None
        fd = os.open(dep_file, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as fh:
            text = fh.read(4 * 1024 * 1024).decode("utf-8", "replace")
    except OSError:
        return None
    rule = text.replace("\\\n", " ").split("\n", 1)[0]
    _, sep, deps = rule.partition(": ")
    if not sep:
        return None
    files = []
    for dep in re.split(r"(?<!\\) +", deps.strip()):
        dep = dep.replace("\\ ", " ")
        if dep.startswith(code_at + "/"):
            files.append(dep[len(code_at) + 1:])
        elif dep and not dep.startswith("/"):
            files.append(os.path.normpath(os.path.join(project, dep)))
    return files


def _mask(text):
    """Rust source with comments, strings, and character literals replaced by spaces (line breaks kept)."""
    out, last = [], 0
    for m in ni._TOKENS["rust"].finditer(text):
        out.append(text[last:m.start()])
        out.append(re.sub(r"[^\n]", " ", m.group(0)))
        last = m.end()
    out.append(text[last:])
    return "".join(out)


def rust_test_spans(text):
    """([(start, end)] of each #[cfg(test)] and #[test] item in Rust source, outermost only: an item inside one
    already left out is part of it; the names of `#[cfg(test)] mod NAME;` file modules). Offsets are into text,
    so a caller that needs positions in the original file reads them here."""
    masked = _mask(text)
    cut, files = [], []
    for m in re.finditer(r"#\s*\[\s*(?:cfg\s*\(\s*test\s*\)|test)\s*\]", masked):
        if cut and m.start() < cut[-1][1]:
            continue  # inside an item already left out (a #[test] in a #[cfg(test)] module)
        i = m.end()
        semi, brace = masked.find(";", i), masked.find("{", i)
        if semi != -1 and (brace == -1 or semi < brace):
            named = re.match(r"\s*(?:pub(?:\([^)]*\))?\s+)?mod\s+(\w+)\s*;", masked[i:semi + 1])
            if named and "cfg" in m.group(0):
                files.append(named.group(1))
            cut.append((m.start(), semi + 1))
            continue
        if brace == -1:
            continue
        depth, j = 0, brace
        while j < len(masked):
            depth += {"{": 1, "}": -1}.get(masked[j], 0)
            if depth == 0:
                break
            j += 1
        cut.append((m.start(), j + 1))
    return cut, files


def _strip_tests(text):
    """(the text with each #[cfg(test)] and #[test] item blanked, line breaks kept; names of
    `#[cfg(test)] mod NAME;`)."""
    cut, files = rust_test_spans(text)
    for start, end in reversed(cut):
        text = text[:start] + re.sub(r"[^\n]", "", text[start:end]) + text[end:]
    return text, files


def _rust_outside_build(rel):
    """Integration tests, benches, and examples, which no build of the program compiles in."""
    return ni.rust_test_source(rel) or "examples" in Path(rel).parts[:-1]


def rust_shipped_sources(code, texts=None, files=None):
    """{relative path: text} of the Rust that goes into the program: the .rs among `files` (cargo_dep_files) when
    given, otherwise every .rs under code outside tests/, benches/, and examples/ less the files that are
    #[cfg(test)] modules; #[cfg(test)] and #[test] items blanked in either. texts ({relative path: text}, from
    ni.source_texts(code, ".rs")) are read when not given."""
    texts = ni.source_texts(code, ".rs") if texts is None else texts
    if files is not None:
        wanted = {f for f in files if f.endswith(".rs")}
        return {rel: _strip_tests(text)[0] for rel, text in texts.items() if rel in wanted}
    shipped, test_files = {}, set()
    for rel, text in texts.items():
        if _rust_outside_build(rel):
            continue
        stripped, modules = _strip_tests(text)
        shipped[rel] = stripped
        p = Path(rel)
        base = p.parent if p.name in ("main.rs", "lib.rs", "mod.rs") else p.parent / p.stem
        for name in modules:
            test_files |= {(base / f"{name}.rs").as_posix(), (base / name / "mod.rs").as_posix()}
    return {k: v for k, v in shipped.items() if k not in test_files}


# Names of the host's Python library and its embedding API: a program that names them can run Python inside its
# own process, where the recorded root sees no start.
PYTHON_EMBED = re.compile(r"libpython|Python\.h\b|\bPy_(?:Initialize\w*|Main|BytesMain|RunMain)\b|\bPyRun_\w+")


def python_embedding(shipped, lang):
    """Shipped files ({relative path: text}) that name the host's Python library or its C API outside comments, or in
    the cgo preamble (a comment) of a Go file that imports "C": a comma-separated list, or "-"."""
    hits = []
    for rel, text in sorted(shipped.items()):
        code = ni.split(text, lang)[0]
        if lang == "go" and re.search(r'(?m)^\s*import\s+"C"', code):
            code = text
        if PYTHON_EMBED.search(code):
            hits.append(rel)
    return ",".join(hits)[:300] or "-"
