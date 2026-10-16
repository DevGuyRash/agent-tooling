"""The overdue list as text or CSV (SPEC R9)."""
import csv
import io


def dollars(cents):
    """Cents as dollars and cents: 150 -> '1.50'."""
    return "%d.%02d" % divmod(cents, 100)


def render_text(rows):
    return "".join(
        "%s  %s  %s  %d  %s\n" % (row.loan, row.member, row.tool, row.days, dollars(row.fine)) for row in rows
    )


def render_csv(rows):
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["loan", "member", "tool", "days", "fine"])
    for row in rows:
        writer.writerow([row.loan, row.member, row.tool, row.days, dollars(row.fine)])
    return out.getvalue()
