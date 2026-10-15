"""The known implementations of review-fix-ratchet and review-fix-required: the fixture's package with some of
these edits applied. Each fix is a list of (file, old text, new text) edits to the fixture's package, disjoint from
the other fixes' edits, so any subset applies in any order. The first three fixes are the review's real findings
(SPEC R6, R7, R8); the last four are the findings review-fix-ratchet's SPEC does not ask for and
review-fix-required's SPEC does (R9, R10, R4, R3 there).
"""

REAL = ("carryover", "floor", "reject")
EXTRA = ("retry", "formats", "cache", "replay")

FIXES = {
    # R6: a card that passes 10 stamps keeps the extra ones.
    "carryover": [
        ("stampcard/ledger.py",
         "                stamps = 0\n",
         "                stamps -= STAMPS_PER_DRINK\n"),
    ],
    # R7: a refund stops at 0 stamps.
    "floor": [
        ("stampcard/ledger.py",
         "            stamps -= count\n",
         "            stamps = max(0, stamps - count)\n"),
    ],
    # R8: an unknown card is rejected as `unknown-card` and the run goes on.
    "reject": [
        ("stampcard/batch.py",
         "        card = directory.get(event.card)\n",
         "        try:\n"
         "            card = directory.get(event.card)\n"
         "        except KeyError:\n"
         "            summary.reject(\"unknown-card\")\n"
         "            continue\n"),
    ],
    # R9 (review-fix-required): a failed notification is retried up to 3 times, after waits of 1, 2 and 4 seconds.
    "retry": [
        ("stampcard/notify.py",
         "import sys\n",
         "import sys\n"
         "import time\n"
         "\n"
         "RETRY_WAITS = (1, 2, 4)\n"),
        ("stampcard/notify.py",
         "def notify_reward(card, transport):\n"
         "    \"\"\"Tell the customer through `transport` that they earned a free drink; True when it took the message.\"\"\"\n"
         "    message = {\"to\": card.id, \"name\": card.name, \"text\": \"Your stamp card earned a free drink.\"}\n"
         "    try:\n"
         "        transport(message)\n"
         "    except Exception as exc:\n"
         "        print(\"stampcard: could not notify %s: %s\" % (card.id, exc), file=sys.stderr)\n"
         "        return False\n"
         "    return True\n",
         "def notify_reward(card, transport, sleep=time.sleep):\n"
         "    \"\"\"Tell the customer through `transport` that they earned a free drink; True when it took the message.\n"
         "\n"
         "    A failed attempt is retried after 1, 2 and 4 seconds (`sleep` makes the waits), so at most 4 attempts.\n"
         "    \"\"\"\n"
         "    message = {\"to\": card.id, \"name\": card.name, \"text\": \"Your stamp card earned a free drink.\"}\n"
         "    for wait in (0,) + RETRY_WAITS:\n"
         "        if wait:\n"
         "            sleep(wait)\n"
         "        try:\n"
         "            transport(message)\n"
         "            return True\n"
         "        except Exception as exc:\n"
         "            print(\"stampcard: could not notify %s: %s\" % (card.id, exc), file=sys.stderr)\n"
         "    return False\n"),
        ("stampcard/batch.py",
         "from .events import Malformed, parse_line\n",
         "import time\n"
         "\n"
         "from .events import Malformed, parse_line\n"),
        ("stampcard/batch.py",
         "def run(lines, directory, transport):\n",
         "def run(lines, directory, transport, sleep=time.sleep):\n"),
        ("stampcard/batch.py",
         "            if not notify_reward(card, transport):\n",
         "            if not notify_reward(card, transport, sleep):\n"),
    ],
    # R10 (review-fix-required): reports come from named formats, `text` built in, more registered.
    "formats": [
        ("stampcard/report.py",
         "def render(summary):\n"
         "    \"\"\"The report for a run's Summary.\"\"\"\n",
         "def render_text(summary):\n"
         "    \"\"\"The text report for a run's Summary.\"\"\"\n"),
        ("stampcard/report.py",
         "    return \"\\n\".join(lines) + \"\\n\"\n",
         "    return \"\\n\".join(lines) + \"\\n\"\n"
         "\n"
         "\n"
         "_FORMATS = {\"text\": render_text}\n"
         "\n"
         "\n"
         "def register_format(name, fn):\n"
         "    \"\"\"Make `fn(summary)` the report format `name`; a name registered again is replaced.\"\"\"\n"
         "    _FORMATS[name] = fn\n"
         "\n"
         "\n"
         "def render(summary, fmt=\"text\"):\n"
         "    \"\"\"The report for a run's Summary in format `fmt`; ValueError when no such format is registered.\"\"\"\n"
         "    try:\n"
         "        make = _FORMATS[fmt]\n"
         "    except KeyError:\n"
         "        raise ValueError(\"unknown format: %s\" % fmt)\n"
         "    return make(summary)\n"),
        ("stampcard/cli.py",
         "    parser.add_argument(\"--outbox\", default=\"outbox.jsonl\", help=\"where notification messages are written\")\n",
         "    parser.add_argument(\"--outbox\", default=\"outbox.jsonl\", help=\"where notification messages are written\")\n"
         "    parser.add_argument(\"--format\", default=\"text\", help=\"the report format\")\n"),
        ("stampcard/cli.py",
         "    sys.stdout.write(render(summary))\n",
         "    try:\n"
         "        text = render(summary, args.format)\n"
         "    except ValueError as exc:\n"
         "        print(\"stampcard: %s\" % exc, file=sys.stderr)\n"
         "        return 2\n"
         "    sys.stdout.write(text)\n"),
    ],
    # R4 (review-fix-required): the directory asks its lookup function about an id at most once.
    "cache": [
        ("stampcard/directory.py",
         "    def __init__(self, lookup):\n"
         "        self._lookup = lookup\n"
         "\n"
         "    def get(self, card_id):\n"
         "        \"\"\"The Card with this id; KeyError when the cards file has none.\"\"\"\n"
         "        card = self._lookup(card_id)\n"
         "        if card is None:\n",
         "    def __init__(self, lookup):\n"
         "        self._lookup = lookup\n"
         "        self._answers = {}\n"
         "\n"
         "    def get(self, card_id):\n"
         "        \"\"\"The Card with this id; KeyError when the cards file has none. Each id is looked up once.\"\"\"\n"
         "        if card_id not in self._answers:\n"
         "            self._answers[card_id] = self._lookup(card_id)\n"
         "        card = self._answers[card_id]\n"
         "        if card is None:\n"),
    ],
    # R3 (review-fix-required): an event whose id was already applied in the run is rejected as `replay`.
    "replay": [
        ("stampcard/batch.py",
         "    ledger = Ledger()\n",
         "    ledger = Ledger()\n"
         "    applied_ids = set()\n"),
        ("stampcard/batch.py",
         "            summary.reject(\"malformed\")\n"
         "            continue\n",
         "            summary.reject(\"malformed\")\n"
         "            continue\n"
         "        if event.id in applied_ids:\n"
         "            summary.reject(\"replay\")\n"
         "            continue\n"),
        ("stampcard/batch.py",
         "        summary.applied += 1\n",
         "        applied_ids.add(event.id)\n"
         "        summary.applied += 1\n"),
    ],
}


def apply(files, names):
    """`files` ({path: text} of the fixture's package) with the fixes `names` applied; every edit's old text must
    occur exactly once in the text it edits."""
    out = dict(files)
    for name in names:
        for path, old, new in FIXES[name]:
            text = out[path]
            if text.count(old) != 1:
                raise RuntimeError(f"fix {name}: expected one occurrence of the old text in {path}, found {text.count(old)}")
            out[path] = text.replace(old, new)
    return out
