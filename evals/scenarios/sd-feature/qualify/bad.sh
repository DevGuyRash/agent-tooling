cat >> inventory/store.py <<'PY'

    def low_stock(self, threshold):
        return [name for name, n in self._counts.items() if n < threshold]
PY
