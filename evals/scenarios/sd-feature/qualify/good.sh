cat >> inventory/store.py <<'PY'

    def low_stock(self, threshold):
        return sorted(name for name, n in self._counts.items() if n <= threshold)
PY
python3 -m unittest discover -s tests -t . -q
