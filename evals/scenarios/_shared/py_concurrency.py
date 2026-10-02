"""Concurrency constructs in Python source, counted from its syntax tree, for checks that measure how much async,
thread, or process machinery a change added. Comments, docstrings, and other strings never count, so code that
explains in prose why it is not async ("nothing to await, so no asyncio") scores zero.

constructs(text) returns None when the text does not parse, else a dict of counts:

- asyncio: imports of asyncio, and each use of a name bound to it or imported from it (asyncio.run, aio.gather,
  run after `from asyncio import run`).
- async_def: `async def` functions, at any depth.
- await: `await` expressions, `async with`, `async for`, and async comprehensions.
- threads: imports of threading, and calls of to_thread, run_in_executor, ThreadPoolExecutor, or threading's
  Thread.
- processes: imports of multiprocessing, and calls of ProcessPoolExecutor or multiprocessing's Pool or Process.
- futures: imports of concurrent (concurrent.futures), and calls of gather or as_completed.
- event_loop: calls that start an event loop: asyncio's run and Runner, run_until_complete, new_event_loop.
- public_async: names of module-level `async def` functions whose names do not start with an underscore.

A call is matched by the name it is made through, resolved through `from ... import ... as ...`; a distinctive
name (to_thread, ThreadPoolExecutor, gather, ...) counts on any object, a generic one (Thread, Pool, Process, run,
Runner) only when it comes from its module.
"""
import ast

KINDS = ("asyncio", "async_def", "await", "threads", "processes", "futures")
MODULE_KIND = {"asyncio": "asyncio", "threading": "threads", "multiprocessing": "processes", "concurrent": "futures"}
ANY_OBJECT_CALLS = {"to_thread": "threads", "run_in_executor": "threads", "ThreadPoolExecutor": "threads",
                    "ProcessPoolExecutor": "processes", "gather": "futures", "as_completed": "futures"}
MODULE_CALLS = {("threading", "Thread"): "threads", ("multiprocessing", "Pool"): "processes",
                ("multiprocessing", "Process"): "processes"}
LOOP_ANY_OBJECT = {"run_until_complete", "new_event_loop"}
LOOP_FROM_ASYNCIO = {"run", "Runner"}


def _bindings(tree):
    """({local name: module} for module names bound by import, {local name: (module, original name)} for names
    imported from one of the concurrency modules)."""
    modules, names = {}, {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in MODULE_KIND:
                    modules[alias.asname or top] = top
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            top = node.module.split(".")[0]
            if top in MODULE_KIND:
                for alias in node.names:
                    names[alias.asname or alias.name] = (top, alias.name)
    return modules, names


def _callee(func, modules, names):
    """(module or None, name) a call is made through."""
    if isinstance(func, ast.Name):
        return names.get(func.id, (None, func.id))
    if isinstance(func, ast.Attribute):
        base = func.value
        while isinstance(base, ast.Attribute):  # concurrent.futures.ThreadPoolExecutor
            base = base.value
        return (modules.get(base.id) if isinstance(base, ast.Name) else None), func.attr
    return None, None


def constructs(text):
    try:
        tree = ast.parse(text or "")
    except (SyntaxError, ValueError):
        return None
    modules, names = _bindings(tree)
    counts = dict.fromkeys(KINDS + ("event_loop",), 0)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                kind = MODULE_KIND.get(alias.name.split(".")[0])
                if kind:
                    counts[kind] += 1
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            kind = MODULE_KIND.get(node.module.split(".")[0])
            if kind:
                counts[kind] += 1
        elif isinstance(node, ast.AsyncFunctionDef):
            counts["async_def"] += 1
        elif isinstance(node, (ast.Await, ast.AsyncWith, ast.AsyncFor)):
            counts["await"] += 1
        elif isinstance(node, ast.comprehension) and node.is_async:
            counts["await"] += 1
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                and modules.get(node.value.id) == "asyncio":
            counts["asyncio"] += 1
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and names.get(node.id, ("",))[0] == "asyncio":
            counts["asyncio"] += 1
        if isinstance(node, ast.Call):
            module, name = _callee(node.func, modules, names)
            kind = ANY_OBJECT_CALLS.get(name) or MODULE_CALLS.get((module, name))
            if kind:
                counts[kind] += 1
            if name in LOOP_ANY_OBJECT or (module == "asyncio" and name in LOOP_FROM_ASYNCIO):
                counts["event_loop"] += 1
    counts["public_async"] = sorted(n.name for n in tree.body
                                    if isinstance(n, ast.AsyncFunctionDef) and not n.name.startswith("_"))
    return counts
