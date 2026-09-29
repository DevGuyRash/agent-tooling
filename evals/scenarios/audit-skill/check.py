import hashlib
import re
from pathlib import Path

ORIGINAL = hashlib.sha256((Path(__file__).parent / "fixture/skills/release-helper/SKILL.md").read_bytes()).hexdigest()


def check(run):
    target = run.workdir / "skills/release-helper/SKILL.md"
    now = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else ""
    reply = run.final_message
    return {
        "target_unchanged": now == ORIGINAL,
        "flags_ask_first": bool(re.search(r"(?is)(ask|confirm|approv).{0,120}(test|build)|(test|build).{0,120}(ask|confirm|approv)", reply)),
        "flags_snapshot": bool(re.search(r"(?i)(stale|as of today|currently red|snapshot|dated|time-sensitive|go(es)? out of date)", reply)),
        "reply_words": len(reply.split()),
    }


def judge_context(run):
    return "The skill under audit:\n" + (Path(__file__).parent / "fixture/skills/release-helper/SKILL.md").read_text()
