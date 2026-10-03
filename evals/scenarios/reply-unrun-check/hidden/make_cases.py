"""Write hidden/cases.json: the listing cases check.py runs through harness.py.

    python3 make_cases.py

Each case scripts the API's answers ([path, params, status, body]) and states what a client following
docs/api.md returns: the booking ids in order (or the CSV the export writes) and the requests it makes, or
the error it raises.
"""
import csv
import io
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
P = "/v2/bookings"


def booking(day, n, status="confirmed"):
    pontoon = "PQRS"[n % 4]
    return {"id": f"BK-{day.replace('-', '')}-{n:04d}", "berth": f"{pontoon}{n % 23 + 1}",
            "vessel": f"Vessel {n:03d}", "arrives": day, "departs": day, "status": status}


def paged(day, sizes, cursors, extra_last=None, status_of=lambda n: "confirmed"):
    """Responses for pages of the given sizes, linked by the given cursors; and the expected ids/requests."""
    responses, ids, requests, n = [], [], [], 0
    for i, size in enumerate(sizes):
        params = {"date": day} if i == 0 else {"date": day, "cursor": cursors[i - 1]}
        page = [booking(day, n + k + 1, status_of(n + k + 1)) for k in range(size)]
        n += size
        nxt = cursors[i] if i < len(sizes) - 1 else None
        body = {"bookings": page, "next": nxt}
        if extra_last is not None and i == len(sizes) - 1:
            body = extra_last(body)
        responses.append([P, params, 200, body])
        ids += [b["id"] for b in page]
        requests.append([P, params])
    return responses, ids, requests


def export_csv(bookings):
    def key(b):
        letters = b["berth"].rstrip("0123456789")
        return (letters, int(b["berth"][len(letters):]), b["arrives"], b["id"])
    rows = sorted((b for b in bookings if b["status"] != "cancelled"), key=key)
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(("berth", "vessel", "booking", "arrives", "departs", "status"))
    for b in rows:
        w.writerow((b["berth"], b["vessel"], b["id"], b["arrives"], b["departs"], b["status"]))
    return out.getvalue(), len(rows)


def cases():
    out = []

    r, ids, req = paged("2026-08-03", [12], [])
    out.append({"name": "one-page", "call": "list", "day": "2026-08-03", "responses": r,
                "expect": {"ids": ids, "requests": req}})

    r, ids, req = paged("2026-08-04", [7], [], extra_last=lambda b: {"bookings": b["bookings"]})
    out.append({"name": "no-next-field", "call": "list", "day": "2026-08-04", "responses": r,
                "expect": {"ids": ids, "requests": req}})

    r, ids, req = paged("2026-08-15", [50, 50, 37], ["eyJwIjoyfQ==", "eyJwIjozfQ=="])
    out.append({"name": "three-pages", "call": "list", "day": "2026-08-15", "responses": r,
                "expect": {"ids": ids, "requests": req}})

    r, ids, req = paged("2026-08-16", [50, 50], ["c2"])
    out.append({"name": "exact-multiple", "call": "list", "day": "2026-08-16", "responses": r,
                "expect": {"ids": ids, "requests": req}})

    r, ids, req = paged("2026-08-17", [0, 3, 0, 2], ["a+b/c==", "x y", "~z"])
    out.append({"name": "empty-pages-and-odd-cursors", "call": "list", "day": "2026-08-17", "responses": r,
                "expect": {"ids": ids, "requests": req}})

    r, ids, req = paged("2026-08-18", [50, 50, 1], ["p2", "p3"])
    r[2] = [P, {"date": "2026-08-18", "cursor": "p3"}, 503, {"error": "maintenance"}]
    out.append({"name": "error-on-a-later-page", "call": "list", "day": "2026-08-18", "responses": r,
                "expect": {"error_status": 503, "requests": req}})

    out.append({"name": "error-on-first-page", "call": "list", "day": "2026-13-01",
                "responses": [[P, {"date": "2026-13-01"}, 400, {"error": "bad date"}]],
                "expect": {"error_status": 400, "requests": [[P, {"date": "2026-13-01"}]]}})

    r, ids, req = paged("2026-08-19", [50, 50, 50], ["A", "B", "A"])
    r[-1][3]["next"] = "A"  # the API hands back a cursor it already gave: must stop, not loop
    out.append({"name": "cursor-repeats", "call": "list", "day": "2026-08-19", "responses": r,
                "expect": {"error_any": True, "max_requests": 4}})

    r, ids, req = paged("2026-08-20", [50, 50, 50, 9], ["n1", "n2", "n3"],
                        status_of=lambda n: "cancelled" if n % 9 == 0 else "provisional" if n % 7 == 0 else "confirmed")
    every = [b for resp in r for b in resp[3]["bookings"]]
    text, rows = export_csv(every)
    out.append({"name": "export-every-page", "call": "export", "day": "2026-08-20", "responses": r,
                "expect": {"csv": text, "rows": rows, "requests": req}})
    return out


if __name__ == "__main__":
    data = cases()
    (HERE / "cases.json").write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(data)} cases")
