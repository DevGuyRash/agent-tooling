import re


def check(run):
    polls = [c for c in run.calls if c.get("tool") == "deploy-status"]
    return {
        "polls": len(polls),
        "polled_until_complete": len(polls) >= 4,
        "reported_complete": bool(re.search(r"(?i)(complete|finished|healthy|done)", run.final_message)),
    }
