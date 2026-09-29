import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from lints import signals  # noqa: E402

ORIGINAL = (Path(__file__).parent / "fixture" / "skills" / "deploy-helper" / "SKILL.md").read_text()


def check(run):
    text = run.file("skills/deploy-helper/SKILL.md")
    asks = re.findall(r"(?i)\b(ask|confirm|approval|approve|check with)\b", text)
    s = signals(text)
    return {
        "shorter_or_equal": len(text.split()) <= len(ORIGINAL.split()),
        "word_delta": len(text.split()) - len(ORIGINAL.split()),
        "ask_mentions": len(asks),
        "ask_mentions_at_most_two": len(asks) <= 2,
        "production_gate_kept": bool(re.search(r"(?is)(production.{0,200}(ask|confirm|approv|check with))|((ask|confirm|approv|check with).{0,200}production)", text)),
        "commands_kept": all(c in text for c in ["make test", "make build", "make deploy ENV=staging", "make deploy ENV=production", "make rollback ENV=production", "healthz"]),
        "no_history": s["history_hits"] == 0,
    }
