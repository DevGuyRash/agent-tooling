"""The plain-text report (SPEC R10)."""


def render(summary):
    """The report for a run's Summary."""
    rejected = sum(summary.rejected.values())
    rejected_line = "rejected: %d" % rejected
    if rejected:
        reasons = ", ".join("%s: %d" % (reason, n) for reason, n in sorted(summary.rejected.items()))
        rejected_line += " (%s)" % reasons
    lines = [
        "stampcard report",
        "events: %d" % summary.events,
        "applied: %d" % summary.applied,
        rejected_line,
        "free drinks: %d" % summary.drinks,
        "notify failed: %d" % summary.notify_failed,
        "cards:",
    ]
    for card_id, stamps, drinks in summary.cards:
        lines.append("  %s  stamps %d  drinks %d" % (card_id, stamps, drinks))
    return "\n".join(lines) + "\n"
