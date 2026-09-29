import subprocess


def check(run):
    status = run.git("status", "--porcelain")
    return {
        "skill_unchanged": "skills/triage" not in status,
        "mentions_testing": any(w in run.final_message.lower() for w in ("untested", "test it", "try it", "trial", "compare", "observe", "measure")),
    }
