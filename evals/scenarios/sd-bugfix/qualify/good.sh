cat > paging.py <<'PY'
def pages(items, size):
    """Split items into pages of at most `size` items, in order."""
    if size <= 0:
        raise ValueError("size must be positive")
    return [items[i:i + size] for i in range(0, len(items), size)]
PY
python3 - <<'PY'
p = "tests/test_paging.py"
s = open(p).read().replace("    def test_empty(self):", "    def test_exact_multiple(self):\n        self.assertEqual(pages([1, 2, 3, 4], 2), [[1, 2], [3, 4]])\n\n    def test_empty(self):")
open(p, "w").write(s)
PY
