"""Reference envflat (docs/envflat.md), used only to compute the expected results in hidden/cases.json."""
import json
import sys

SAFE = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-./:@+,%")


class Fail(Exception):
    pass


class Number(str):
    pass


class Pairs(list):
    pass


def reject_constant(name):
    raise ValueError(f"{name} is not valid JSON")


def component(name):
    return "".join(c.upper() if c.isascii() and c.isalnum() else "_" for c in name)


def render(value):
    if value is None:
        return ""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, Number):
        return str(value)
    if value and all(c in SAFE for c in value):
        return value
    return "'" + value.replace("'", "'\\''") + "'"


def flatten(value, path, out, seen):
    if isinstance(value, Pairs):
        for name, member in value:
            flatten(member, path + [component(name)], out, seen)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            flatten(item, path + [str(i)], out, seen)
    else:
        key = "__".join(path)
        if key in seen:
            raise Fail(f"duplicate key {key}")
        seen.add(key)
        if isinstance(value, str) and not isinstance(value, Number) and any(ord(c) < 0x20 or ord(c) == 0x7F for c in value):
            raise Fail(f"{key}: control character in value")
        out.append(f"{key}={render(value)}")


def main(argv):
    prefix, files, i = None, [], 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--prefix":
            if i + 1 >= len(argv):
                print("envflat: --prefix needs a NAME", file=sys.stderr)
                return 2
            prefix = argv[i + 1]
            i += 2
            continue
        if arg.startswith("--prefix="):
            prefix = arg[len("--prefix="):]
        elif arg.startswith("-") and arg != "-":
            print(f"envflat: unknown option {arg}", file=sys.stderr)
            return 2
        else:
            files.append(arg)
        i += 1
    if len(files) > 1:
        print("envflat: more than one FILE", file=sys.stderr)
        return 2
    name = files[0] if files else "-"
    try:
        if name == "-":
            raw = sys.stdin.buffer.read()
        else:
            try:
                with open(name, "rb") as f:
                    raw = f.read()
            except OSError as e:
                raise Fail(f"cannot read {name}: {e.strerror}")
        try:
            text = raw.decode("utf-8")
            doc = json.loads(text, object_pairs_hook=Pairs, parse_float=Number, parse_int=Number,
                             parse_constant=reject_constant)
        except (UnicodeDecodeError, ValueError) as e:
            raise Fail(f"invalid JSON: {e}")
        if not isinstance(doc, Pairs):
            raise Fail("the document is not an object")
        out = []
        flatten(doc, [component(prefix)] if prefix is not None else [], out, set())
    except Fail as e:
        print(f"envflat: {e}", file=sys.stderr)
        return 1
    sys.stdout.write("".join(line + "\n" for line in out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
