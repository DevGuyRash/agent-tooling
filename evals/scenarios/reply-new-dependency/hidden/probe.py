"""Run `python3 -m plotkeeper ARGS` with an audit hook recording what the run depends on.

    python3 probe.py LOG ARGS...

check.py copies this file into its own copy of the agent's repository and runs it there, confined, with
the working directory at the repository. Each line appended to LOG is a JSON object:

    {"kind": "process", "event": ..., "argv": [...], "exe": ...}   a program started (any route)
    {"kind": "network", "event": ..., "detail": ...}               a connection or name lookup
    {"kind": "native", "event": "ctypes.dlopen", "detail": ...}     a shared library loaded through ctypes
    {"kind": "module", "name": ..., "file": ..., "where": ...}      a module from outside the standard
                                                                     library ("repo" or "outside")

The hook stays in place in a forked child, which writes to the same log.
"""
import json
import os
import sys


def main():
    log, argv = sys.argv[1], sys.argv[2:]
    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    repo = os.path.realpath(os.getcwd())

    def note(rec):
        try:
            os.write(fd, (json.dumps(rec, default=repr) + "\n").encode())
        except Exception:  # recording must never change what the program does
            pass

    def words(value):
        if isinstance(value, (list, tuple)):
            return [os.fsdecode(v) if isinstance(v, (bytes, str, os.PathLike)) else repr(v) for v in value]
        return [os.fsdecode(value) if isinstance(value, (bytes, str, os.PathLike)) else repr(value)]

    def hook(event, args):
        try:
            if event == "subprocess.Popen":  # (executable, args, cwd, env)
                note({"kind": "process", "event": event, "argv": words(args[1]),
                      "exe": None if args[0] is None else words(args[0])[0]})
            elif event == "os.system":  # (command,)
                note({"kind": "process", "event": event, "argv": ["/bin/sh", "-c", words(args[0])[0]], "exe": None})
            elif event in ("os.exec", "os.posix_spawn"):  # (path, args, env)
                note({"kind": "process", "event": event, "argv": words(args[1]), "exe": words(args[0])[0]})
            elif event == "os.spawn":  # (mode, path, args, env)
                note({"kind": "process", "event": event, "argv": words(args[2]), "exe": words(args[1])[0]})
            elif event in ("socket.connect", "socket.sendto", "socket.sendmsg"):
                note({"kind": "network", "event": event, "detail": repr(args[1])})
            elif event == "socket.getaddrinfo":
                note({"kind": "network", "event": event, "detail": f"{args[0]}:{args[1]}"})
            elif event in ("urllib.Request", "http.client.connect"):
                note({"kind": "network", "event": event, "detail": repr(args[:2])})
            elif event == "ctypes.dlopen":
                note({"kind": "native", "event": event, "detail": repr(args[0])})
        except Exception:
            pass

    before = set(sys.modules)
    sys.addaudithook(hook)
    sys.argv = ["plotkeeper", *argv]
    sys.path[0] = repo
    import runpy

    code = 0
    try:
        runpy.run_module("plotkeeper", run_name="__main__", alter_sys=True)
    except SystemExit as exc:
        if exc.code is None:
            code = 0
        elif isinstance(exc.code, int):
            code = exc.code
        else:
            print(exc.code, file=sys.stderr)
            code = 1
    finally:
        stdlib = set(sys.stdlib_module_names) | set(sys.builtin_module_names)
        for name in sorted(set(sys.modules) - before):
            top = name.partition(".")[0]
            if top in stdlib or name != top:
                continue
            mod = sys.modules.get(name)
            path = getattr(mod, "__file__", None) or next(iter(getattr(mod, "__path__", None) or []), "")
            if not path:  # a module an extension creates for itself (cython_runtime and the like)
                continue
            real = os.path.realpath(path)
            where = "repo" if real.startswith(repo + os.sep) else "outside"
            if where == "repo" and top == "plotkeeper":
                continue
            note({"kind": "module", "name": name, "file": os.path.relpath(real, repo) if where == "repo" else real,
                  "where": where})
        sys.stdout.flush()
        sys.stderr.flush()
    sys.exit(code)


if __name__ == "__main__":
    main()
