python3 - <<'PY'
import re
s = open("utils.py").read()
s = s.replace('def chunk(items, size):\n    """Split a list into consecutive lists of at most `size` items."""\n    raise NotImplementedError  # TODO',
              'def chunk(items, size):\n    return [items[i:i + size] for i in range(0, len(items), size)]')
open("utils.py", "w").write(s)
PY
