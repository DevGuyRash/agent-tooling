"""Alternative dedupe step a contributor drafted last week: same behavior, backed by a set
instead of a list, so membership checks don't get slower as more ids are seen. Not wired
into the pipeline yet.
"""


def dedupe(records):
    seen = set()
    result = []
    for record in records:
        key = record["id"]
        if key not in seen:
            seen.add(key)
            result.append(record)
    return result
