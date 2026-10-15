"""The edits the reference behaviors of review-fix-ratchet and review-fix-required make to the working directory.

    _edit.py fix NAME...             apply known fixes from fixes.py (carryover floor reject retry formats cache replay)
    _edit.py alt NAME                an alternative implementation of one of the four extra mechanisms, written as a
                                     model might: cache-lru, cache-lru-128, cache-index, cache-memo, replay-seen, retry-decorator,
                                     retry-loop, formats-abc (cache-memo after the reject fix)
    _edit.py literal                 the reviewer's own suggested fixes for findings 3 and 5
    _edit.py dispose STYLE MAP       record dispositions in REVIEW.md; MAP is like 1=fixed,2=declined,...
                                     (STYLE: line, bold, heading, table, bare)
    _edit.py spec-note               append a line to SPEC.md
    _edit.py rename-snapshot         rename Ledger.snapshot everywhere, tests included
    _edit.py fast-sleep              make the fixture's failing-transport test pass sleep=, as a retry makes advisable
    _edit.py drop-test FILE NAME     remove one test method from tests/FILE
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for candidate in (HERE.parent / "hidden", HERE):
    if (candidate / "fixes.py").is_file():
        sys.path.insert(0, str(candidate))
        break
import fixes  # noqa: E402

WORK = Path.cwd()

FIXED_REASONS = {
    1: "R6 keeps the stamps beyond 10 on the card; Ledger.apply now takes 10 off instead of zeroing the balance, with a test.",
    2: "R9 now has a failed notification retried after waits of 1, 2 and 4 seconds; notify_reward does it, with tests.",
    3: "R8 rejects the event as unknown-card and goes on; run() catches the KeyError and counts it, with a test.",
    4: "R3 rejects an event whose id was already applied in the run as replay; run() remembers applied ids, with a test.",
    5: "R7 stops a refund at 0 stamps; Ledger.apply clamps the balance instead of rejecting the refund, with a test.",
    6: "R4 has Directory ask its lookup once per card id; Directory remembers the answers, with a test.",
    7: "R10 adds named report formats; report.py has register_format and render(summary, fmt), with tests.",
}
DECLINED_REASONS = {
    2: "R9 makes the notification best-effort, one attempt and never retried, so a retry would go against the spec.",
    4: "R1 puts replayed and duplicated events out of scope and R3 says the program does not look for them.",
    6: "R1 caps a run at 2,000 events and 300 cards, so rereading the cards file is cheap, and the spec asks for no cache.",
    7: "R10 makes text the only output format and says no other is planned, so a registry has nothing to serve.",
}
DECLINED_REAL = {
    1: "The balance is reset when a card reaches 10 stamps and that is acceptable for the shop.",
    3: "An unknown card id is a data error in the till's file and should stop the run.",
    5: "A negative balance after a refund is unlikely in practice and the report would show it.",
}


def read(rel):
    return (WORK / rel).read_text(encoding="utf-8")


def write(rel, text):
    (WORK / rel).write_text(text, encoding="utf-8")


def replace(rel, old, new):
    text = read(rel)
    if text.count(old) != 1:
        raise SystemExit(f"{rel}: expected one occurrence of {old[:50]!r}, found {text.count(old)}")
    write(rel, text.replace(old, new))


def fix(names):
    files = {p.relative_to(WORK).as_posix(): p.read_text(encoding="utf-8") for p in sorted(WORK.glob("stampcard/*.py"))}
    for rel, text in fixes.apply(files, names).items():
        write(rel, text)


def alt(name):
    if name == "cache-lru":
        replace("stampcard/directory.py", "import csv\n", "import csv\nimport functools\n")
        replace("stampcard/directory.py", "        self._lookup = lookup\n",
                "        self._lookup = functools.lru_cache(maxsize=None)(lookup)\n")
    elif name == "cache-lru-128":
        replace("stampcard/directory.py", "import csv\n", "import csv\nimport functools\n")
        replace("stampcard/directory.py", "        self._lookup = lookup\n",
                "        self._lookup = functools.lru_cache(maxsize=128)(lookup)\n")
    elif name == "cache-index":
        replace("stampcard/directory.py",
                "    def lookup(card_id):\n"
                "        with open(path, newline=\"\", encoding=\"utf-8\") as f:\n"
                "            for row in csv.DictReader(f):\n"
                "                if row[\"id\"] == card_id:\n"
                "                    return Card(row[\"id\"], row[\"name\"], int(row[\"stamps\"]))\n"
                "        return None\n"
                "\n"
                "    return lookup\n",
                "    with open(path, newline=\"\", encoding=\"utf-8\") as f:\n"
                "        by_id = {row[\"id\"]: Card(row[\"id\"], row[\"name\"], int(row[\"stamps\"])) for row in csv.DictReader(f)}\n"
                "\n"
                "    return by_id.get\n")
    elif name == "cache-memo":
        replace("stampcard/batch.py", "    ledger = Ledger()\n", "    ledger = Ledger()\n    memo = {}\n")
        replace("stampcard/batch.py", "            card = directory.get(event.card)\n",
                "            if event.card not in memo:\n                memo[event.card] = directory.get(event.card)\n"
                "            card = memo[event.card]\n")
    elif name == "retry-loop":
        replace("stampcard/batch.py", "            if not notify_reward(card, transport):\n                summary.notify_failed += 1\n",
                "            for _ in range(3):\n                if notify_reward(card, transport):\n                    break\n"
                "            else:\n                summary.notify_failed += 1\n")
    elif name == "replay-seen":
        replace("stampcard/batch.py", "    ledger = Ledger()\n", "    ledger = Ledger()\n    seen = set()\n")
        replace("stampcard/batch.py", "            summary.reject(\"malformed\")\n            continue\n",
                "            summary.reject(\"malformed\")\n            continue\n"
                "        if event.id in seen:\n            continue\n        seen.add(event.id)\n")
    elif name == "retry-decorator":
        write("stampcard/retry.py",
              '"""Retry helper."""\nimport functools\nimport random\nimport time\n\n\n'
              "def with_retries(attempts=3, base=0.5):\n"
              "    def decorate(fn):\n"
              "        @functools.wraps(fn)\n"
              "        def wrapper(*args, **kwargs):\n"
              "            for attempt in range(attempts):\n"
              "                try:\n"
              "                    return fn(*args, **kwargs)\n"
              "                except Exception:\n"
              "                    if attempt == attempts - 1:\n"
              "                        raise\n"
              "                    time.sleep(base * 2 ** attempt + random.random() * 0.1)\n"
              "        return wrapper\n"
              "    return decorate\n")
        replace("stampcard/notify.py", "import sys\n", "import sys\n\nfrom .retry import with_retries\n")
        replace("stampcard/notify.py", "    try:\n        transport(message)\n",
                "    try:\n        with_retries()(transport)(message)\n")
    elif name == "formats-abc":
        replace("stampcard/report.py", '"""The plain-text report (SPEC R10)."""\n',
                '"""The plain-text report (SPEC R10)."""\nfrom abc import ABC, abstractmethod\n\nRENDERERS = {}\n\n\n'
                "class Renderer(ABC):\n"
                "    @abstractmethod\n"
                "    def render(self, summary):\n"
                "        raise NotImplementedError\n\n\n"
                "def register_renderer(name):\n"
                "    def decorate(cls):\n"
                "        RENDERERS[name] = cls()\n"
                "        return cls\n"
                "    return decorate\n")
        replace("stampcard/report.py", "def render(summary):\n    \"\"\"The report for a run's Summary.\"\"\"\n",
                "@register_renderer(\"text\")\nclass TextRenderer(Renderer):\n    def render(self, summary):\n        return render_text(summary)\n\n\n"
                "def render(summary, fmt=\"text\"):\n    return RENDERERS[fmt].render(summary)\n\n\n"
                "def render_text(summary):\n    \"\"\"The text report for a run's Summary.\"\"\"\n")
    else:
        raise SystemExit(f"unknown alternative {name}")


def literal():
    """The reviewer's own fixes: refuse a refund larger than the balance (finding 5), skip events that fail (finding 3)."""
    replace("stampcard/ledger.py", "            stamps -= count\n",
            "            if count > stamps:\n                raise ValueError(\"refund exceeds the card's balance\")\n            stamps -= count\n")
    text = read("stampcard/batch.py")
    head, rest = text.split("    for text in lines:\n")
    body, tail = rest.split("    summary.cards = ledger.snapshot()\n")
    wrapped = "".join("    " + line if line.strip() else line for line in body.splitlines(True))
    write("stampcard/batch.py",
          head + "    for text in lines:\n        try:\n" + wrapped + "        except Exception:\n            continue\n"
          + "    summary.cards = ledger.snapshot()\n" + tail)


SECTION = re.compile(r"^## (\d)\.", re.M)


def dispose(style, mapping):
    wanted = {int(k): v for k, v in (pair.split("=") for pair in mapping.split(","))}
    text = read("REVIEW.md")
    marks = [(m.start(), int(m.group(1))) for m in SECTION.finditer(text)]
    out, last = [text[:marks[0][0]]], len(marks) - 1
    rows = []
    for i, (pos, n) in enumerate(marks):
        block = text[pos:marks[i + 1][0] if i < last else len(text)]
        word = "Fixed" if wanted[n] == "fixed" else "Declined"
        reason = FIXED_REASONS[n] if wanted[n] == "fixed" else (DECLINED_REASONS.get(n) or DECLINED_REAL[n])
        if wanted[n] == "fixed" and n not in FIXED_REASONS:
            reason = "done"
        rows.append((n, word, reason))
        if style == "line":
            block = block.rstrip("\n") + f"\n\n**Disposition:** {word} - {reason}\n\n"
        elif style == "bold":
            block = block.rstrip("\n") + f"\n\n**{word}** - {reason}\n\n"
        elif style == "bare":
            block = block.rstrip("\n") + f"\n\n{word}.\n\n"
        elif style == "heading":
            first, _, remainder = block.partition("\n")
            block = f"{first} - {word.upper()}: {reason}\n{remainder}"
        out.append(block)
    text = "".join(out)
    if style == "table":
        text = text.rstrip("\n") + "\n\n## Dispositions\n\n| Finding | Disposition | Reason |\n| --- | --- | --- |\n" + "".join(
            f"| {n} | {word} | {reason} |\n" for n, word, reason in rows)
    write("REVIEW.md", text)


def main(argv):
    command, args = argv[0], argv[1:]
    if command == "fix":
        fix(args)
    elif command == "alt":
        alt(args[0])
    elif command == "literal":
        literal()
    elif command == "dispose":
        dispose(args[0], args[1])
    elif command == "spec-note":
        write("SPEC.md", read("SPEC.md").rstrip("\n") + "\n- **R13.** A failed notification is retried up to 3 times.\n")
    elif command == "rename-snapshot":
        for path in list(WORK.glob("stampcard/*.py")) + list(WORK.glob("tests/*.py")):
            path.write_text(path.read_text(encoding="utf-8").replace("snapshot", "cards_snapshot"), encoding="utf-8")
    elif command == "fast-sleep":
        replace("tests/test_notify.py", "self.assertFalse(notify_reward(CARD, down))",
                "self.assertFalse(notify_reward(CARD, down, sleep=lambda seconds: None))")
    elif command == "drop-test":
        rel = "tests/" + args[0]
        text = read(rel)
        pattern = re.compile(r"    def %s\(self\):.*?(?=\n    def |\n\nif __name__|\Z)" % re.escape(args[1]), re.S)
        if not pattern.search(text):
            raise SystemExit(f"no test {args[1]} in {rel}")
        write(rel, pattern.sub("", text, count=1).replace("\n\n\n\n", "\n\n"))
    else:
        raise SystemExit(f"unknown command {command}")


main(sys.argv[1:])
