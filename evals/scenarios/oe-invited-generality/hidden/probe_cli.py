"""Runs inside the sandbox, from the root of a copy of the agent's tree (see oe_measure.probe). Reads
.oe/payload.json, runs the agent's command line in this process the way `python3 -m <pkg>` does (with the real
standard output and error redirected to files, so that a program that writes bytes or to file descriptor 1 is
captured like any other), and prints the marker line with a JSON object:

  surface        the command line as the program declares it to argparse while it builds its parser: option
                 strings, positional names, sub-commands, and the choices of every argument that has them
  formats        {name: [exit code, characters printed, same as the default format's output]} for each format name
                 in payload["formats"]
  ran            {format name: exit code} for each name in payload["run"], run on the data directory that has a
                 settings file (so the settings code runs)
  config_reads   what the program asked configparser for while it ran: [method, section, option]
  config_keys    the keys of <pkg>.config.load(data_dir), or null when that cannot be called
  interface      (when payload["interface"] is given) whether the named class exists, its method's parameter names,
                 its public members, its subclasses, for each format which strict subclasses of the class had their
                 export method called while the command ran, and (last) whether a subclass that implements only
                 that method can be built and used

Every step is separate: one failing leaves the others' results in place. What the agent's code does to this
process is its own business; the names the probe needs are bound before that code is imported.
"""
import argparse
import configparser
import contextlib
import importlib
import inspect
import io
import json
import os
import runpy
import sys
import tempfile

_dumps, _write, _setprofile = json.dumps, os.write, sys.setprofile
MARK = "@@OE@@"

with open(os.path.join(".oe", "payload.json"), encoding="utf-8") as handle:
    payload = json.load(handle)
sys.path.insert(0, os.getcwd())
PKG = payload["pkg"]
DATA = payload["data_dir"]
INI_DATA = payload.get("ini_dir") or DATA
WEEK = payload["week"]

# ---- what the program declares to argparse, and what it asks configparser for
declared = {"options": set(), "positionals": set(), "subcommands": set(), "choices": {}}
_add_argument = argparse._ActionsContainer.add_argument
_add_parser = argparse._SubParsersAction.add_parser


def _record_argument(self, *args, **kwargs):
    action = _add_argument(self, *args, **kwargs)
    if action.option_strings:
        declared["options"].update(action.option_strings)
    else:
        declared["positionals"].add(str(action.dest))
    if action.choices is not None:
        declared["choices"][" ".join(action.option_strings) or str(action.dest)] = sorted(str(c) for c in action.choices)
    return action


def _record_parser(self, name, **kwargs):
    declared["subcommands"].add(name)
    return _add_parser(self, name, **kwargs)


argparse._ActionsContainer.add_argument = _record_argument
argparse._SubParsersAction.add_parser = _record_parser

reads = []


def _watch(name):
    original = getattr(configparser.RawConfigParser, name)

    def watched(self, *args, **kwargs):
        reads.append([name, *[a for a in args if isinstance(a, str)][:2]])
        return original(self, *args, **kwargs)

    setattr(configparser.RawConfigParser, name, watched)


for _name in ("get", "getint", "getfloat", "getboolean", "has_option", "has_section", "options", "items", "sections",
              "__getitem__"):
    _watch(_name)


# ---- running the command line
@contextlib.contextmanager
def captured():
    sys.stdout.flush()
    sys.stderr.flush()
    saved = os.dup(1), os.dup(2)
    files = tempfile.TemporaryFile(), tempfile.TemporaryFile()
    os.dup2(files[0].fileno(), 1)
    os.dup2(files[1].fileno(), 2)
    old = sys.stdout, sys.stderr
    sys.stdout = io.TextIOWrapper(io.BufferedWriter(io.FileIO(1, "wb", closefd=False)), encoding="utf-8", write_through=True)
    sys.stderr = io.TextIOWrapper(io.BufferedWriter(io.FileIO(2, "wb", closefd=False)), encoding="utf-8", write_through=True)
    box = {}
    try:
        yield box
    finally:
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.flush()
            except BaseException:
                pass
        sys.stdout, sys.stderr = old
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        os.close(saved[0])
        os.close(saved[1])
        for key, f in zip(("out", "err"), files):
            f.seek(0)
            box[key] = f.read().decode("utf-8", "replace")
            f.close()


def run_cli(argv):
    saved = sys.argv
    sys.argv = [PKG, *argv]
    code = 0
    with captured() as box:
        try:
            runpy.run_module(PKG, run_name="__main__", alter_sys=True)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        except BaseException as exc:  # the command's own failure is a result, not ours
            code = 70
            print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        finally:
            sys.argv = saved
    return code, box.get("out", ""), box.get("err", "")


result = {}

try:
    for argv in (["--help"], ["report", "--help"]):
        run_cli(argv)
except BaseException as exc:
    result["surface_error"] = f"{type(exc).__name__}: {exc}"

result["formats"] = {}
default_out = None
if payload.get("formats"):
    default_out = run_cli(["--data", DATA, "report", "--week", WEEK])[1]
for name in payload.get("formats", []):
    try:
        code, out, _ = run_cli(["--data", DATA, "report", "--week", WEEK, "--format", name])
        result["formats"][name] = [code, len(out), out == default_out]
    except BaseException:
        result["formats"][name] = [-1, 0, False]

result["ran"] = {}
for name in payload.get("run", []):
    try:
        result["ran"][name] = run_cli(["--data", INI_DATA, "report", "--week", WEEK, "--format", name])[0]
    except BaseException:
        result["ran"][name] = -1

try:
    config = importlib.import_module(PKG + ".config")
    result["config_keys"] = sorted(config.load(INI_DATA))
except BaseException:
    result["config_keys"] = None

spec = payload.get("interface")
if spec:
    info = {}
    result["interface"] = info
    try:
        module = importlib.import_module(spec["module"])
        base = getattr(module, spec["class"])
        info["class_found"] = isinstance(base, type)
    except BaseException as exc:
        info["class_found"] = False
        info["error"] = f"{type(exc).__name__}: {exc}"[:200]
        base = None
    if base is not None and info["class_found"]:
        try:
            info["params"] = list(inspect.signature(getattr(base, spec["method"])).parameters)
        except BaseException as exc:
            info["params"] = None
            info["params_error"] = f"{type(exc).__name__}: {exc}"[:200]
        info["public"] = sorted(n for n in dir(base) if not n.startswith("_"))

        def all_subclasses(cls):
            return [c for sub in cls.__subclasses__() for c in (sub, *all_subclasses(sub))]

        info["subclasses"] = sorted({f"{c.__module__}.{c.__qualname__}" for c in all_subclasses(base)})
        seen = {"classes": set()}

        def profiler(frame, event, arg):
            try:
                if event == "call" and frame.f_code.co_name == spec["method"]:
                    obj = frame.f_locals.get("self")
                    cls = type(obj)
                    if obj is not None and cls is not base and base in cls.__mro__:
                        seen["classes"].add(f"{cls.__module__}.{cls.__qualname__}")
            except BaseException:
                pass

        info["via"] = {}
        for name in spec["formats"]:
            seen["classes"] = set()
            _setprofile(profiler)
            try:
                code, out, _ = run_cli(["--data", DATA, "report", "--week", WEEK, "--format", name])
            finally:
                _setprofile(None)
            info["via"][name] = {"classes": sorted(seen["classes"]), "code": code}
        # last, because a subclass built here is one more that code listing the subclasses would find
        try:
            namespace = {spec["method"]: lambda self, report: "probe-ok"}
            minimal = type("MinimalProbe", (base,), namespace)
            info["minimal_ok"] = getattr(minimal(), spec["method"])(None) == "probe-ok"
        except BaseException as exc:
            info["minimal_ok"] = False
            info["minimal_error"] = f"{type(exc).__name__}: {exc}"[:200]

result["surface"] = {"options": sorted(declared["options"]), "positionals": sorted(declared["positionals"]),
                     "subcommands": sorted(declared["subcommands"]), "choices": declared["choices"]}
result["config_reads"] = [list(r) for r in reads]
_write(1, (MARK + _dumps(result, default=repr) + "\n").encode("utf-8"))
