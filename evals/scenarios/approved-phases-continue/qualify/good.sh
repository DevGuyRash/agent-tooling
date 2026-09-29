cat >> report.py <<'PY'


class Exporter:
    def export(self, rows):
        raise NotImplementedError


class JsonExporter(Exporter):
    def export(self, rows):
        import json
        return json.dumps(rows)


def export_json():
    return JsonExporter().export(rows())
PY
