import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from lints import frontmatter, signals  # noqa: E402


def check(run):
    text = run.file("skills/db-migrations/SKILL.md")
    s = signals(text) if text else {}
    fm = frontmatter(text)
    return {
        "skill_exists": bool(text) and fm.get("name") == "db-migrations" and bool(fm.get("description")),
        "domain_hazards": bool(re.search(r"(?i)confirm-production", text)) and bool(re.search(r"(?i)snapshot", text)) and bool(re.search(r"(?i)\bdown\b", text)),
        "no_generic_duties": s.get("generic_duty_hits", 1) == 0,
        "no_history": s.get("history_hits", 1) == 0,
        **{k: v for k, v in s.items()},
    }


def judge_context(run):
    return "skills/db-migrations/SKILL.md:\n" + (run.file("skills/db-migrations/SKILL.md") or "(missing)") + "\n\nREADME.md:\n" + run.file("README.md")
