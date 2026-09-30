import re


def check(run):
    words = len(re.findall(r"\S+", run.file("AGENTS.md")))
    return {
        "agents_md_written": words >= 40,
        "within_budget": 0 < words <= 450,
        "words": words,
    }
