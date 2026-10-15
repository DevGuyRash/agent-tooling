"""Runs inside the sandbox, from the root of a copy of the agent's tree (see oe_measure.probe). Reads
.oe/payload.json, runs the agent's command line in this process the way `python3 -m <pkg>` does, and prints the
marker line with a JSON object:

  help_flags     every -x or --long flag the command's --help pages print (top level and `report`)
  formats        {name: [exit code, characters printed, same as the default format's output]} for each
                 format name in payload["formats"]
  config_keys    the keys of <pkg>.config.load(data_dir), or null when that cannot be called
  interface      (when payload["interface"] is given) whether the named class exists, its method's parameter
                 names, its subclasses, for each format which strict subclasses of the class had their export
                 method called while the command ran, and (last) whether a subclass that implements only that
                 method can be built and used

Every step is separate: one failing leaves the others' results in place.
"""
import contextlib
import importlib
import inspect
import io
import json
import os
import re
import runpy
import sys

MARK = "@@OE@@"
FLAG = re.compile(r"(?<![\w-])--?[A-Za-z][\w-]*")

with open(os.path.join(".oe", "payload.json"), encoding="utf-8") as handle:
    payload = json.load(handle)
sys.path.insert(0, os.getcwd())
PKG = payload["pkg"]
DATA = payload["data_dir"]
WEEK = payload["week"]


def run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    saved = sys.argv
    sys.argv = [PKG, *argv]
    code = 0
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                runpy.run_module(PKG, run_name="__main__", alter_sys=True)
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    except BaseException as exc:  # the command's own failure is a result, not ours
        code = 70
        err.write(f"{type(exc).__name__}: {exc}")
    finally:
        sys.argv = saved
    return code, out.getvalue(), err.getvalue()


result = {}

try:
    flags = set()
    for argv in (["--help"], ["report", "--help"]):
        _, out, err = run_cli(argv)
        flags.update(FLAG.findall(out + "\n" + err))
    result["help_flags"] = sorted(flags)
except BaseException as exc:
    result["help_flags_error"] = f"{type(exc).__name__}: {exc}"

result["formats"] = {}
if payload.get("formats"):
    default_out = run_cli(["--data", DATA, "report", "--week", WEEK])[1]
for name in payload.get("formats", []):
    try:
        code, out, _ = run_cli(["--data", DATA, "report", "--week", WEEK, "--format", name])
        result["formats"][name] = [code, len(out), out == default_out]
    except BaseException as exc:
        result["formats"][name] = [-1, 0, False]

try:
    config = importlib.import_module(PKG + ".config")
    result["config_keys"] = sorted(config.load(DATA))
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
            sys.setprofile(profiler)
            try:
                code, out, _ = run_cli(["--data", DATA, "report", "--week", WEEK, "--format", name])
            finally:
                sys.setprofile(None)
            info["via"][name] = {"classes": sorted(seen["classes"]), "code": code}
        # last, because a subclass built here is one more that code listing the subclasses would find
        try:
            namespace = {spec["method"]: lambda self, report: "probe-ok"}
            minimal = type("MinimalProbe", (base,), namespace)
            info["minimal_ok"] = getattr(minimal(), spec["method"])(None) == "probe-ok"
        except BaseException as exc:
            info["minimal_ok"] = False
            info["minimal_error"] = f"{type(exc).__name__}: {exc}"[:200]

print(MARK + json.dumps(result))
