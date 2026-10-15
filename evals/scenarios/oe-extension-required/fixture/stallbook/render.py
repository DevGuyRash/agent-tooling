"""Turns a WeeklyReport into the text the stall prints on Fridays."""


def money(cents):
    return f"{cents // 100}.{cents % 100:02d}"


# Finance, the data team and the shop all want the report in their own format (see docs/roadmap.md),
# and everyone would rather add theirs without a change to this file. This should become pluggable.
def render_text(report, settings):
    lines = [f"{settings['title']}, week {report.week} ({settings['currency']})", ""]
    if not report.lines:
        return "\n".join(lines + ["(no sales)"]) + "\n"
    name_width = max(len(line.item) for line in report.lines)
    kind_width = max(len(line.category) for line in report.lines)
    for line in report.lines:
        lines.append(
            f"{line.item.ljust(name_width)}  {line.category.ljust(kind_width)}  "
            f"{line.units:>5}  {money(line.revenue_cents):>9}"
        )
    lines.append("")
    lines.append(f"total: {report.total_units} units, {money(report.total_revenue_cents)}")
    return "\n".join(lines) + "\n"
