"""Original dedupe step: straightforward, but re-scans the ids seen so far for every record."""


def dedupe(records):
    seen = []
    result = []
    for record in records:
        key = record["id"]
        if key not in seen:
            seen.append(key)
            result.append(record)
    return result
