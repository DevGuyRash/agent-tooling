cat > utils.py <<'PY'
import re


def slugify(title):
    return "-".join(re.findall(r"[a-z0-9]+", title.lower()))


def chunk(items, size):
    return [items[i:i + size] for i in range(0, len(items), size)]


def parse_duration(text):
    units = {"h": 3600, "m": 60, "s": 1}
    return sum(int(n) * units[u] for n, u in re.findall(r"(\d+)([hms])", text))
PY
