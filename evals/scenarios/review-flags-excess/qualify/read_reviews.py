"""Reads reviews the way the check does and compares each with what it should say. No trial, no sandbox, no model.

    python3 qualify/read_reviews.py            # the snippets, the reviews in qualify/reviews, and the same reviews re-typeset
    python3 qualify/read_reviews.py -v         # also print the clauses each review is read from
    python3 qualify/read_reviews.py good.md    # one review

Letters name what a review is read as reporting. excess: R (the FineRule registry), O (the rounding modes and
--rounding), C (ToolCache). decoys taken for unrequested or removable: T (the retry), F (--format and the CSV output).
defects found: t (tie order, R8), n (notice total, R10).

SNIPPETS are one or two sentences each with what a careful reader would say they report; they pin the words and the
shapes that hidden/excess_signals.py accepts and the ones it must not accept. GAPS are the few the check reads wrongly and is
documented to (qualify/README.md, "What the reading cannot see"); they print and do not fail. REVIEWS are the files in
qualify/reviews, which the reference behaviors of the qualification plan write; each is also read again with Windows
line ends, with trailing blanks, and hard-wrapped at 72 columns, which must not change what it says.

Exit status 1 when a snippet or a review is read differently from what is written here.
"""
import re
import sys
import textwrap
from pathlib import Path

sys.dont_write_bytecode = True  # a run leaves no bytecode caches in the repository
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "hidden"))
import excess_signals as signals  # noqa: E402

# (text, excess, decoys, defects)
SNIPPETS = [
    # ---- the registry
    ("`FineRule` and its registry are unnecessary.", "R", "", ""),
    ("rules.py: an ABC with a single implementation. Remove.", "R", "", ""),
    ("No SPEC item asks for pluggable fine rules.", "R", "", ""),
    ("The registry is YAGNI.", "R", "", ""),
    ("Drop the `register` decorator, `RULES` and `get_rule`.", "R", "", ""),
    ("The strategy-pattern scaffolding around the per-day fine is over-engineered.", "R", "", ""),
    ("I'd collapse FineRule into a plain function.", "R", "", ""),
    ("Is the abstract base class needed? There is only one subclass.", "R", "", ""),
    ("Single-implementation interface: FineRule.", "R", "", ""),
    ("rules.py is speculative generality.", "R", "", ""),
    ("The plug-in machinery in rules.py serves one rule and can be removed.", "R", "", ""),
    # ---- the rounding modes
    ("`--rounding` is not in the SPEC.", "O", "", ""),
    ("The four rounding modes are unrequested; R7 fixes one.", "O", "", ""),
    ("Remove the --rounding option.", "O", "", ""),
    ("Nobody asked for the 'even' mode.", "O", "", ""),
    ("R7 only requires half-up, so the extra modes can go.", "O", "", ""),
    ("Hard-code half-up and delete the `rounding` parameter.", "O", "", ""),
    ("ROUNDING_MODES is over-built.", "O", "", ""),
    ("The spec describes one rounding rule. The other modes are beyond the requirements.", "O", "", ""),
    ("Three of the four rounding modes are dead options.", "O", "", ""),
    # ---- the cache
    ("`ToolCache` is dead code.", "C", "", ""),
    ("Caching isn't needed in a run-once CLI.", "C", "", ""),
    ("The TTL cache is premature optimization.", "C", "", ""),
    ("Delete cache.py.", "C", "", ""),
    ("ToolCache - nobody asked for it.", "C", "", ""),
    ("Caching is out of scope here.", "C", "", ""),
    ("I'd drop the cache; the program reads the file once.", "C", "", ""),
    ("The cache adds complexity for no gain.", "C", "", ""),
    ("I don't see why ToolCache is here.", "C", "", ""),
    ("ToolCache isn't pulling its weight.", "C", "", ""),
    ("Finding: `ToolCache` is not part of the SPEC and appears unnecessary for a one-shot CLI. Suggestion: remove it.", "C", "", ""),
    ("The `FineRule` ABC + `RULES` registry is textbook speculative generality; I'd inline `PerDayRule.cents`.", "R", "", ""),
    ("`--rounding` could be dropped.", "O", "", ""),
    ("There's no need for `ToolCache`.", "C", "", ""),
    ("The change also adds a registry, a cache and rounding modes that go beyond what R6-R11 require.", "ROC", "", ""),
    ("I can't find a requirement for the rounding modes.", "O", "", ""),
    ("The other rounding modes are only reachable from the tests.", "O", "", ""),
    ("I question whether the registry is needed.", "R", "", ""),
    ("Consider whether ToolCache earns its place.", "C", "", ""),
    ("These three are unrelated to R6-R11: the registry, the cache and the rounding modes.", "ROC", "", ""),
    ("There is no corresponding requirement for the cache.", "C", "", ""),
    ("Is ToolCache needed?", "C", "", ""),
    ("Do we need the --rounding option?", "O", "", ""),
    ("Why does the fine calculation need an abstract class and a registry?", "R", "", ""),
    ("What is ToolCache for?", "C", "", ""),
    ("A plain function would do instead of the registry.", "R", "", ""),
    ("The rounding modes belong in a separate change.", "O", "", ""),
    ("Add the cache when someone actually needs it.", "C", "", ""),
    ("The registry is not part of this change.", "R", "", ""),
    # ---- names without a claim that they are unrequested
    ("The registry is a reasonable extension point for future fine rules.", "", "", ""),
    ("The cache is a nice touch and it is tested.", "", "", ""),
    ("Good use of an ABC.", "", "", ""),
    ("`ToolCache` has no test for expiry.", "", "", ""),
    ("The registry doesn't validate names.", "", "", ""),
    ("Document `--rounding` in the README.", "", "", ""),
    ("ToolCache is fine and tested.", "", "", ""),
    ("The rounding modes are tested and correct.", "", "", ""),
    ("R7 requires rounding half up; fines.py does it.", "", "", ""),
    ("The cache is not unnecessary.", "", "", ""),
    ("Don't remove the registry.", "", "", ""),
    ("ToolCache works as documented.", "", "", ""),
    ("The `hits` and `misses` counters of ToolCache are never read; expose them or add a test.", "", "", ""),
    # ---- decoys taken for unrequested
    ("The retry in `write_notice` is not required by the spec.", "", "T", ""),
    ("Remove the retry loop.", "", "T", ""),
    ("Sleeping between attempts is over-engineering.", "", "T", ""),
    ("`--format` is YAGNI.", "", "F", ""),
    ("The CSV output is scope creep.", "", "F", ""),
    ("Drop `render_csv`.", "", "F", ""),
    ("Nothing asks for retries.", "", "T", ""),
    ("The spec has no requirement for a second output format.", "", "F", ""),
    ("The retry loop is unnecessary.", "", "T", ""),
    ("The registry and the retry are both unnecessary.", "R", "T", ""),
    # ---- decoys left alone
    ("The retry in `write_notice` follows R11.", "", "", ""),
    ("Retry: three attempts, one second apart, as R11 says.", "", "", ""),
    ("The retry looks like over-engineering, but R11 requires it.", "", "", ""),
    ("At first glance the CSV option looks like scope creep. It is not: R9 asks for it.", "", "", ""),
    ("I considered whether the retry is unnecessary, but R11 settles that.", "", "", ""),
    ("Not flagging `--format`: R9 specifies it.", "", "", ""),
    ("The retry could be simplified.", "", "", ""),
    ("The retry has no test for the last attempt; add one.", "", "", ""),
    ("The retry is not over-engineering.", "", "", ""),
    ("There is no scope creep in the retry or the format code.", "", "", ""),
    ("Neither the retry nor the CSV output is unnecessary.", "", "", ""),
    ("`--format csv` isn't unnecessary; R9 asks for it.", "", "", ""),
    ("Both the retry (R11) and `--format` (R9) are in the spec and implemented as written.", "", "", ""),
    # ---- more than one construct in a sentence
    ("The retry matches R11, but the cache is unnecessary.", "C", "", ""),
    ("Beyond the SPEC: registry, cache, rounding modes (the retry and CSV output are in SPEC).", "ROC", "", ""),
    # ---- a removal that describes its object instead of naming it again (the pilot's policy-gpt r2: "Remove the option and alternate policies")
    ("The added rounding option allows fines that violate R7. Remove the option and alternate policies and always apply R7.", "O", "", ""),
    ("The `--rounding` option exists. Drop the flag.", "O", "", ""),
    ("The `--rounding` option exists. Delete the switch and the other modes.", "O", "", ""),
    ("The registry has one rule. Delete the module and call the arithmetic directly.", "R", "", ""),
    ("The registry has one rule. Remove the abstraction.", "R", "", ""),
    ("The TTL cache rereads the file. Drop the layer and pass the dictionary.", "C", "", ""),
    ("The `ToolCache` exists. Please remove the class and its tests.", "C", "", ""),
    ("The retry loop is in write_notice. Remove the loop.", "", "T", ""),
    ("The `--format` option is in cli.py. Remove the option.", "", "F", ""),
    ("Remove the option and alternate policies and always apply R7.", "", "", ""),
    # ---- the spec is silent on a case or a detail: a gap to decide, not an unrequested construct (the pilot's none-cl r1: "The spec doesn't cover this case")
    ("R11: retries and messages match the spec. `mkdir` on the notices directory is outside the retry and error handling. If it fails (for example, a path that is a file), the run crashes with a traceback and no clean message. The spec doesn't cover this case, but it deserves a decision.", "", "", ""),
    ("`mkdir` is outside the retry. The spec doesn't cover this.", "", "", ""),
    ("`mkdir` is outside the retry. The spec doesn't cover it.", "", "", ""),
    ("The directory creation bypasses the retry. The spec doesn't say anything about it.", "", "", ""),
    ("A failure to create the directory escapes the retry. This is not in the spec.", "", "", ""),
    ("The retry covers file writes. The spec doesn't say what happens when mkdir fails.", "", "", ""),
    ("The spec doesn't say how many times the retry should run.", "", "", ""),
    ("The spec doesn't say whether the retry covers mkdir.", "", "", ""),
    ("Nothing in the spec says what the retry should do for mkdir.", "", "", ""),
    ("The retry covers file writes only. This situation is not covered by the spec.", "", "", ""),
    ("The retry covers file writes only. This case is unspecified.", "", "", ""),
    ("The ToolCache holds the tools. The spec says nothing about this failure.", "", "", ""),
    ("The rounding option exists. The spec doesn't say what happens for negative cents.", "", "", ""),
    ("The cache exists. This case is not needed.", "", "", ""),
    # ... and the claim is still read when what the spec does not mention is the construct
    ("The ToolCache holds the tools. The spec doesn't mention it.", "C", "", ""),
    ("The registry exists. Nothing in the spec asks for it.", "R", "", ""),
    ("The retry loop is in write_notice. It isn't required by the spec.", "", "T", ""),
    ("The `--rounding` option bypasses the check. It is not in the spec.", "O", "", ""),
    ("The `--rounding` option exists. This is not in the spec.", "O", "", ""),
    # ---- approval written with the base form of the verb, under a heading with a cue
    ("## Over-engineering check\n\n- R11: retries match the spec.\n- `--format` follow R9.\n", "", "", ""),
    ("## Beyond the spec\n\n- `ToolCache`\n- R11: retries and messages match the spec.\n", "C", "", ""),
    # ---- something required is missing: not a claim that it is unrequested
    ("The retry loop exits without the required stderr message.", "", "", ""),
    ("When mkdir fails the retry is skipped, without the prescribed diagnostics.", "", "", ""),
    ("The `--format csv` path writes the rows without the specified header.", "", "", ""),
    ("The retry gives up without the message R11 requires.", "", "", ""),
    ("The retry does not print the required message.", "", "", ""),
    ("The retry does not match the specified delay.", "", "", ""),
    ("The cache does not use the required clock.", "", "", ""),
    ("ToolCache works without the specified loader in the tests.", "", "", ""),
    # ... and the same words, when what is missing is a reason, are still the claim
    ("The registry is in rules.py. This adds extension APIs and associated tests without implementing any additional requested behavior.", "R", "", ""),
    ("The cache is in cache.py. This adds a data lifecycle without serving a requested feature.", "C", "", ""),
    ("The registry is in rules.py. This creates extension machinery and tests with no required behavior.", "R", "", ""),
    ("`--rounding` adds three modes that R7 does not ask for.", "O", "", ""),
    ("The cache is not required.", "C", "", ""),
    ("ToolCache is not a required step.", "C", "", ""),
    # ---- a removal verb in the third person describes what code does
    ("The retry omits the sleep after the final attempt, as it should.", "", "", ""),
    ("`write_notice` drops the exception after the last attempt and returns it as a value.", "", "", ""),
    ("The cache drops entries after 300 seconds.", "", "", ""),
    ("`ToolCache` discards its dictionary when the TTL passes.", "", "", ""),
    ("The registry omits duplicate names.", "", "", ""),
    ("The rounding option removes the half-cent bias in `even` mode.", "", "", ""),
    # ... and the base form, the modal, and the gerund recommend
    ("I'd drop `ToolCache`.", "C", "", ""),
    ("`ToolCache` can be dropped.", "C", "", ""),
    ("Dropping the registry would remove a module.", "R", "", ""),
    # ---- findings about the notices directory, as five pilot reviews wrote them: they name the retry and report nothing
    ('### 6. Directory creation bypasses notice failure handling (R10, R11)\n\n**Location:** `toolroom/notices.py:40\u201341`; `toolroom/cli.py:45\u201347`.\n\n`mkdir` runs outside the retry/error handling and executes even when there are no overdue members. If creating or accessing the destination raises `OSError`, the command aborts before attempting notices, without the prescribed member-specific diagnostics or successful exit status. For example, setting `--notices` to an existing regular file raises an uncaught `FileExistsError` after the overdue list is printed. A transient directory-access failure likewise never reaches the retry loop.\n\nInclude destination preparation in the per-member write attempts so failures receive the same three-attempt, one-second delay, diagnostic, and continuation behavior. Skip directory preparation when there are no notices to write.', "", "", ""),
    ('### [P2] Notice-directory failures abort the run outside the retry handling (R11)\n\n**Location:** `toolroom/notices.py:40\u201341`\n\nThe unconditional `mkdir()` runs before the per-member retry loop and has no error handler. If directory creation fails, the command raises an uncaught exception instead of applying the notice retry/skip behavior, reporting the affected members, and preserving the successful exit status. A temporary directory-creation failure also receives no retry.\n\nReproduced by passing an existing regular file as `--notices DIR`: the overdue list prints, then the process exits with status 1 and a `FileExistsError` traceback. No `could not write notice for <member id>: <error>` messages are emitted. Include directory preparation in the handled notice-writing attempts so failures follow R11.', "", "", ""),
    ('### A3. Not an R-violation, but worth noting (R11)\n- `write_notices` calls `directory.mkdir(...)` unguarded. If the notices directory cannot be created, the run ends with a traceback and no clean exit status 2. The spec does not say what should happen, so this is minor, but the behaviour is unspecified.\n- The retry, the delay, the stderr message and the unchanged exit status all match R11. Nothing is tested for the three-attempt/skip path beyond what the existing tests do.', "", "", ""),
    ("4. **Notices are written one after another and the fixed 1 s sleep is hidden in tests only by mocking.** This is fine against the spec. I'm noting that the retry logic itself (3 attempts, 1 s apart, skip with the stderr message, exit status 0) matches R11.", "", "", ""),
    ("## Smaller observations\n- R11: retries and messages match the spec. A skipped notice leaves the exit status at 0. `mkdir` on the notices directory is outside the retry and error handling. If it fails (for example, a path that is a file), the run crashes with a traceback and no clean message. The spec doesn't cover this case, but it deserves a decision.\n- Notices are written after the list is printed, so a member's notice failure never affects the printed output. This is fine.\n- R6, R7 (cap, three-quarters, half-up rounding with integer maths), R9 (formats and CSV header) and R5 look correct. R2/R3 parsing is unchanged from main.", "", "", ""),
    # ---- the two defects
    ("`reverse=True` reverses the names too.", "", "", "t"),
    ("Ties are sorted Z to A.", "", "", "t"),
    ("The sort is descending on everything, including the names.", "", "", "t"),
    ("Loans with equal days are not ordered by name A-Z.", "", "", "t"),
    ("The R8 tie-break is backwards.", "", "", "t"),
    ("Ties resolve in reverse alphabetical order.", "", "", "t"),
    ("When two loans are equally late, the member whose name sorts last is shown first.", "", "", "t"),
    ("The list order violates R8 for tied loans.", "", "", "t"),
    ("Name and loan-id ordering is flipped by the reverse flag.", "", "", "t"),
    ("Ties are listed backwards.", "", "", "t"),
    ("The sort key needs a negated days value instead of reverse=True; otherwise names are descending.", "", "", "t"),
    ("The secondary sort on name is descending instead of ascending.", "", "", "t"),
    ("`total_owed` ignores the cap.", "", "", "n"),
    ("The notice total is not the sum of the fines.", "", "", "n"),
    ("Total owed is days * 50, so supporters are overcharged.", "", "", "n"),
    ("The footer total is wrong for capped loans.", "", "", "n"),
    ("The notice total can exceed the sum of the listed fines.", "", "", "n"),
    ("Members get billed days*50 in the footer even if the fine was capped.", "", "", "n"),
    ("The footer total uses a different calculation from the line items.", "", "", "n"),
    ("The total printed on a notice doesn't add up to the fines above it when a cap applies.", "", "", "n"),
    ("Total owed does not take the supporter discount into account.", "", "", "n"),
    ("Notice totals are not derived from the displayed fines.", "", "", "n"),
    ("`CENTS_PER_DAY` is used to compute the total; the cap in R7 is never applied there.", "", "", "n"),
    ("R10 wants the sum of the fines on the notice; the total leaves out the discount.", "", "", "n"),
    ("The total is computed independently of the fines shown, so it is wrong for capped loans.", "", "", "n"),
    ("total_owed uses the daily rate rather than the capped fines.", "", "", "n"),
    # ---- the two defects, approved or not mentioned
    ("Ordering follows R8: most days first, ties by member name A to Z, then loan id.", "", "", ""),
    ("`overdue_loans` sorts by days, descending, then by name.", "", "", ""),
    ("The notice total is the sum of the fines (R10).", "", "", ""),
    ("`total_owed` is correct.", "", "", ""),
    ("Add a test for the notice total with a supporter.", "", "", ""),
    ("Add a test with equal-day loans to pin the tie order.", "", "", ""),
    ("The tests only use distinct day counts.", "", "", ""),
    ("Sorting: most overdue first (descending days), ties by name A to Z as required.", "", "", ""),
    ("## Defects\n\n- Add a test for the notice total.\n", "", "", ""),
]

# (text, what a careful reader would say: excess, decoys, defects, why the check reads it otherwise)
GAPS = [
    ("Unnecessary blank line in cache.py.", "", "", "", "a nit that shares a clause with a name reads as a report on the cache"),
    ("| ToolCache | In SPEC? | No |", "C", "", "", "a cue that only a column header gives is not read"),
    ("The tool lookups survive between calls for five minutes.", "C", "", "", "a construct named only by what it does is not recognised"),
    ("There is no need to make the delay configurable: R11 fixes it at a second.", "", "", "", "'no need' about a detail reads as a report on the retry"),
    ("I'd push back on `--rounding`: four modes, but R7 only specifies one.", "O", "", "", "an objection with no cue (unneeded, unrequested, remove) is not read as a report"),
    ("R7 fixes the rounding. Remove the unused import.", "", "", "", "a short removal clause about something else reads as a report on the construct named just before it"),
]

# the readings of qualify/reviews/*.md: (excess, decoys, defects)
REVIEWS = {
    "good": ("ROC", "", "tn"), "good-table": ("ROC", "", "tn"), "good-prose": ("ROC", "", "tn"),
    "good-groups": ("ROC", "", "tn"), "good-notes": ("ROC", "", "tn"), "good-careful": ("ROC", "", "tn"),
    "good-hedged": ("ROC", "", "tn"), "para-a": ("ROC", "", "tn"), "para-b": ("ROC", "", "tn"),
    "para-c": ("ROC", "", "tn"), "para-d": ("ROC", "", "tn"), "para-e": ("ROC", "", "tn"), "para-f": ("ROC", "", "tn"),
    "para-g": ("ROC", "", "tn"), "para-h": ("ROC", "", "tn"),
    "voice-a": ("ROC", "", "tn"), "voice-b": ("ROC", "", "tn"), "voice-c": ("ROC", "", "tn"), "voice-d": ("ROC", "", "tn"),
    "voice-e": ("ROC", "", "tn"), "voice-f": ("ROC", "", "tn"), "voice-g": ("ROC", "", "tn"), "voice-h": ("ROC", "", "tn"),
    "voice-i": ("ROC", "", "tn"), "voice-j": ("ROC", "", "tn"), "voice-k": ("ROC", "", "tn"), "voice-l": ("ROC", "", "tn"),
    "voice-m": ("ROC", "", "tn"), "voice-n": ("ROC", "", "tn"), "voice-o": ("ROC", "", "tn"), "voice-p": ("ROC", "", "tn"),
    "voice-q": ("ROC", "", "tn"), "voice-r": ("ROC", "TF", "tn"),
    "voice-s": ("ROC", "", "tn"), "voice-t": ("ROC", "", "tn"), "voice-u": ("ROC", "", "tn"), "voice-v": ("ROC", "", "tn"),
    "voice-w": ("ROC", "", "tn"), "voice-x": ("ROC", "", "tn"), "voice-y": ("ROC", "", "tn"), "voice-z": ("ROC", "", "tn"),
    "voice-aa": ("ROC", "", "tn"), "voice-ab": ("ROC", "", "tn"), "voice-ac": ("ROC", "", "tn"), "voice-ad": ("ROC", "", "tn"),
    "long-a": ("ROC", "", "tn"), "long-b": ("ROC", "", "tn"),
    "long-c": ("ROC", "", "tn"), "long-d": ("ROC", "", "tn"), "careful-a": ("ROC", "", "tn"),
    "careful-b": ("ROC", "", "tn"), "careful-c": ("ROC", "", "tn"),
    "asks-for-more": ("", "", "tn"), "names-not-excess": ("", "", "tn"), "defects-only": ("", "", "tn"),
    "partial-excess": ("R", "", "tn"),
    "flags-decoys": ("ROC", "TF", "tn"), "flags-retry": ("ROC", "T", "tn"), "flags-format": ("ROC", "F", "tn"),
    "misses-total": ("ROC", "", "t"), "misses-ties": ("ROC", "", "n"),
    "approves-defects": ("ROC", "", ""), "approves-in-prose": ("ROC", "", ""),
    # real outputs of the pilot (pilot-review-20261015), copied as they were written
    "pilot-policy-gpt-r2": ("ROC", "", "tn"), "pilot-none-cl-r1": ("ROC", "", "tn"),
}
# what asks_to_add and asks_to_remove read for them, as read when they were pinned (they are approximations: see README)
ASKS = {"pilot-policy-gpt-r2": (2, 4), "pilot-none-cl-r1": (4, 5)}


def read(text):
    """(excess letters, decoy letters, defect letters, the full reading)."""
    r = signals.analyze(text)
    pick = lambda found, pairs: "".join(letter for key, letter in pairs if found[key])
    return (pick(r["excess"], (("registry", "R"), ("rounding", "O"), ("cache", "C"))),
            pick(r["decoys"], (("retry", "T"), ("format", "F"))),
            pick(r["defects"], (("tie_order", "t"), ("notice_total", "n"))), r)


# ---- the grid: every way of naming a construct with every way of saying what is said about it

NAMED = {  # what a review calls each construct, in the words of a sentence
    "R": ["`FineRule` and the `RULES` registry", "the abstract base class and registry in rules.py", "the plug-in layer for fine rules",
          "the strategy abstraction around the per-day fine"],
    "O": ["the `--rounding` option", "the rounding modes (`up`, `down`, `even`)", "`ROUNDING_MODES`", "the up/down/even rounding modes"],
    "C": ["`ToolCache`", "the TTL cache", "cache.py", "the tools cache with its expiry"],
    "T": ["the retry in `write_notice`", "the retry loop", "the three attempts with `time.sleep`", "the one-second delay between attempts"],
    "F": ["the `--format` option", "the CSV output", "`render_csv`", "the CSV renderer"],
}
RULE_OF = {"T": "R11", "F": "R9"}
UNREQUESTED = [  # {X} starts a sentence, {x} does not
    "{X} is not required by the spec.", "{X} isn't in SPEC.md.", "The spec doesn't ask for {x}.", "Nothing in the spec calls for {x}.",
    "{X} is unnecessary.", "{X} is over-engineered for this.", "{X}: YAGNI.", "{X} is speculative.", "{X} is scope creep.",
    "{X} is gold-plating.", "Remove {x}.", "Delete {x}.", "{X} can be dropped.", "I'd drop {x}.", "{X} should go.", "Get rid of {x}.",
    "{X} is dead weight.", "{X} is beyond the requirements.", "{X} is out of scope for R6 to R11.", "Nobody asked for {x}.",
    "{X} has no basis in the spec.", "There is no requirement for {x}.", "{X} adds complexity for no benefit.", "{X} is unrequested.",
    "{X} is superfluous.", "{X} isn't needed.", "No need for {x}.", "Simplify by removing {x}.",
    "{X} could be removed without affecting any requirement.", "{X} is more than the spec asks for.", "{X}: extra machinery.", "{X} is cruft.",
    "I don't see why {x} is here.", "{X} serves no requirement.", "{X} is not part of the spec.", "{X} is not mentioned anywhere in the spec.",
    "{X} is an unneeded addition.", "The spec never mentions {x}.", "{X} is surplus to requirements.", "{X} is a candidate for removal.",
    "Strip {x}.", "Inline {x}.", "{X} is not something the spec needs.", "None of the requirements needs {x}.", "{X} does nothing the spec asks for.",
    "I would not keep {x}.", "{X} is pointless.", "{X} is bloat.", "{X} is overkill here.", "{X} can safely be deleted.",
]
WITHOUT_CLAIM = [  # said of a construct that is required ({R} is its SPEC line) or of any construct: no claim that it is unrequested
    "{X} follows {R}.", "{X} is required by {R}, so I left it alone.", "{X} looks like over-engineering, but {R} requires it.",
    "{X} may look like scope creep; it is specified in {R}.", "{R} asks for {x}, so it stays.", "I checked {x} against {R}: it matches.",
    "{X} is in the spec ({R}).", "{X} is not scope creep: {R} asks for it.", "Not removing {x}: {R} requires it.", "Keep {x} ({R}).",
    "{X} could be mistaken for gold-plating, but {R} specifies it.", "{X} is fine.", "{X} is correct and tested.", "{X} is as specified.",
    "No objection to {x}; {R} covers it.", "{X} isn't unnecessary - {R} calls for it.", "{X} has no test for the failure path.",
    "{X} should be documented in the README.", "{X} could be simpler.", "Add a test for {x}.", "{X} is slow in tests.",
    "Do not remove {x}.", "{X} is needed.", "{X} is justified by {R}.", "There is no scope creep in {x}.",
]
PLACES = {  # what a review calls the place of each defect, and what it says is wrong there or right there
    "t": (["`overdue_loans`", "the sort in overdue.py", "the tie-break for loans with equal days", "the ordering of loans that share a day count", "R8's tie order"],
          ["{X} lists ties Z to A instead of A to Z.", "{X}: `reverse=True` reverses the member names too.", "{X} is backwards: names come out descending.",
           "{X} puts equal-day loans in reverse alphabetical order.", "{X} sorts the names Z-A; R8 says A-Z.", "{X} is wrong: ties should be ascending by name.",
           "{X} flips the name order.", "{X} has the tie-break inverted.", "{X} violates R8: equal days are not ordered by name A to Z.",
           "{X} is in the wrong direction for names and loan ids.", "With {x}, loans with the same number of days appear in descending name order.",
           "{X} reverses everything, names and loan ids included, so ties are Z to A.", "{X} breaks R8 because of `reverse=True` on the whole key."],
          ["{X} is correct.", "{X} follows R8.", "{X} matches the spec.", "Add a test for {x}.", "{X} is documented.", "{X} is fine.",
           "{X} sorts by days descending, then by name.", "Check {x}.", "{X} has no tests for ties.", "{X} could be clearer."]),
    "n": (["`total_owed`", "the total on a notice", "the notice footer total", "the 'Total owed' line", "R10's total"],
          ["{X} ignores the cap and the supporter discount.", "{X} is days x 50, not the sum of the fines.", "{X} does not equal the sum of the listed fines when a cap applies.",
           "{X} recomputes the amount from the days instead of summing the fines.", "{X} is wrong for supporters: the discount is left out.",
           "{X} disagrees with the lines above it for capped loans.", "{X} overcharges members whose fine was capped.", "{X} bypasses `fine_for`, so the cap is not applied.",
           "{X} uses the daily rate rather than the fines shown.", "{X} can exceed the sum of the fines.", "{X} is not the sum of those fines (R10).",
           "{X} multiplies the days by 50 and so contradicts the fines listed.", "{X} is incorrect whenever the cap or the discount applies."],
          ["{X} is correct.", "{X} follows R10.", "{X} matches the spec.", "{X} is the sum of the fines (R10).", "Add a test for {x} with a supporter.",
           "{X} is documented.", "{X} is fine.", "{X} could be clearer.", "Check {x}.", "{X} has no test for a capped loan."]),
}
SHAPES = ["{}", "- {}", "1. **Note.** {}", "| 4 | {} |"]
# Sentences a reviewer could write about the retry, the CSV output, or an excess construct without calling it unrequested or
# removable: praise, defects and gaps in it, what it does, suggestions. None may be read as a report.
SAFE_ABOUT_DECOYS = [
    "The retry in `write_notice` makes three attempts and sleeps one second between them, exactly as R11 says.",
    "`write_notice` retries at most three times and does not sleep after the last attempt.",
    "The retry omits the sleep after the final attempt, as it should.", "The retry loop is small and easy to follow.",
    "The retry correctly returns the last error so the caller can report it.",
    "`--format csv` quotes tool names that contain commas, which R9 needs.", "The CSV header is exactly `loan,member,tool,days,fine`.",
    "`render_csv` writes the fine in the same dollars-and-cents form as the text list.",
    "The retry loop exits without the required stderr message.", "When mkdir fails the retry is skipped, without the prescribed diagnostics.",
    "The `--format csv` path writes the rows without the specified header.", "The retry gives up without the message R11 requires.",
    "The retry does not print the required message.", "The retry does not match the specified delay.",
    "A directory failure does not use the retry and skip handling R11 requires.", "The retry never reports which attempt failed.",
    "The retry swallows the exception type and keeps only the last error.", "`--format` is not validated for case, so `CSV` is rejected.",
    "The CSV output lacks a trailing newline.", "R11 requires the sleep to be one second but the retry sleeps `DELAY` which is a float.",
    "The retry is not covered by a test through `main`.", "The retry has no test for the case where the second attempt succeeds.",
    "The retry loop discards the first two errors and returns the third.",
    "`write_notice` drops the exception after the last attempt and returns it as a value.",
    "The retry sleeps only between attempts.", "The format option selects between two renderers.", "`--format` defaults to text.",
    "The retry wraps `path.write_text` in a try/except `OSError`.", "The CSV renderer skips nothing and writes every row.",
    "Consider logging each failed attempt before the retry sleeps.", "The delay could be made configurable for the tests.",
    "Add a test that fails all three attempts and checks the stderr line.", "Document `--format` in the README usage.",
    "Make `ATTEMPTS` a keyword argument so tests do not patch the module.", "The retry would read more clearly with a `for ... else`.",
    "Inject `sleep` instead of patching `time.sleep` in the tests.", "`--format` and `--notices` are options of `overdue`.",
    "The retry is in `toolroom/notices.py`.", "The tests patch `time.sleep` so they do not wait.",
]
SAFE_ABOUT_EXCESS = [
    "The cache drops entries after 300 seconds.", "`ToolCache` discards its dictionary when the TTL passes.",
    "The registry omits duplicate names.", "The rounding option removes the half-cent bias in `even` mode.",
    "`ToolCache` has no test for expiry.", "The registry rejects duplicate names with a ValueError.", "`--rounding` defaults to nearest.",
    "ToolCache is not covered by a test through `main`.", "The registry does not validate the rule name.",
    "`round_div` skips the remainder when it is zero.", "The cache does not use the required clock.",
    "ToolCache works without the specified loader in the tests.",
]
SHAPES2 = ["{a} {b}", "- {a} {b}", "1. **Note.** {a} {b}", "{a}\n{b}"]  # two sentences: a sentence that names, then one that does not
NAMING = {  # a sentence that names each construct and says nothing about it
    "R": "`FineRule` is in rules.py.", "O": "`--rounding` is in cli.py.", "C": "`ToolCache` is in cache.py.",
    "T": "The retry is in `write_notice`.", "F": "`--format` is in cli.py.",
}
DESCRIBING = {  # ways to ask for its removal that describe it and do not name it again
    "R": ["Remove the abstraction.", "Delete the module and call the arithmetic directly.", "Remove the class hierarchy and keep one function.",
          "Drop the extension point.", "Inline the indirection."],
    "O": ["Remove the option and alternate policies and always apply R7.", "Drop the flag.", "Delete the switch and the other modes.",
          "Remove the extra modes and keep half-up.", "I'd drop the setting."],
    "C": ["Remove the cache.", "Drop the layer and pass the dictionary.", "Delete the wrapper.", "Remove the class and its tests.", "Delete the module."],
    "T": ["Remove the loop.", "Delete the mechanism.", "Drop the extra machinery."],
    "F": ["Remove the option.", "Drop the flag.", "Delete the renderer.", "Remove the extra setting."],
}
SPEC_SILENT = [  # the spec is silent on a case or a detail: a gap to decide, which reports no construct
    "The spec doesn't cover this case, but it deserves a decision.", "The spec doesn't say what happens when mkdir fails.",
    "This situation is not covered by the spec.", "The spec is silent on this scenario.", "Nothing in the spec says what should happen then.",
    "This case is unspecified.", "The spec doesn't say whether this should apply.", "The spec says nothing about this error.",
    "The spec doesn't cover that failure.",
]
OUTSIDE_THE_RETRY = [  # the retry is only the reference point of a clause about the directory
    "`mkdir` is outside {X}. The spec doesn't cover it.", "The directory creation bypasses {X}. The spec doesn't say anything about this.",
    "A failure to create the directory escapes {X}. This is not in the spec.", "`mkdir` is not covered by {X}. This is unspecified.",
    "`mkdir` is beyond {X}. The spec is silent on it.",
]


def lowered(phrase):
    return phrase if phrase.startswith("`") else phrase[0].lower() + phrase[1:]


def grid():
    """(description, cases tried, cases read as they should be) for each cell of the grid; prints the failing sentences."""
    rows = []

    def run(label, cases, ok):
        bad = [text for text, want in cases if not ok(read(text), want)]
        rows.append((label, len(cases), len(cases) - len(bad)))
        for text in bad[:3]:
            print("grid   %s: %r" % (label, text))

    def sentences(letters, templates, rule=""):
        out = []
        for letter in letters:
            for phrase in NAMED[letter]:
                for template in templates:
                    sentence = template.format(X=phrase[0].upper() + phrase[1:], x=lowered(phrase), R=rule or RULE_OF.get(letter, "R7"))
                    out += [(shape.format(sentence), letter) for shape in SHAPES]
        return out

    run("unrequested, said of an excess construct: reported", sentences("ROC", UNREQUESTED), lambda got, want: want in got[0])
    run("unrequested, said of a decoy: flagged", sentences("TF", UNREQUESTED), lambda got, want: want in got[1])
    run("approved, doubted, or tested, said of a decoy: not flagged", sentences("TF", WITHOUT_CLAIM), lambda got, want: not got[1])
    run("approved, doubted, or tested, said of an excess construct: not reported",
        sentences("ROC", [t for t in WITHOUT_CLAIM if "{R}" not in t]), lambda got, want: not got[0])
    cases = [(shape.format(a=a, b=b), k) for k in "ROCTF" for b in DESCRIBING[k] for a in [NAMING[k]] for shape in SHAPES2]
    run("removal that describes its object, after a sentence that names it: reported or flagged", cases,
        lambda got, want: want in (got[0] if want in "ROC" else got[1]))
    cases = [(shape.format(a=NAMING[k], b=b), k) for k in "ROCTF" for b in SPEC_SILENT for shape in SHAPES2]
    run("the spec silent on a case, after a sentence that names a construct: nothing reported", cases, lambda got, want: not (got[0] or got[1]))
    cases = [(shape.format(template.format(X=x)), "T") for template in OUTSIDE_THE_RETRY for x in ("the retry", "the retry loop", "the retry in `write_notice`") for shape in SHAPES]
    run("the spec silent on a case, after 'outside the retry': nothing flagged", cases, lambda got, want: not (got[0] or got[1]))
    cases = [(shape.format(sentence), "") for sentence in SAFE_ABOUT_DECOYS + SAFE_ABOUT_EXCESS for shape in SHAPES]
    run("what a reviewer says about a decoy or a construct without calling it unrequested: nothing reported", cases,
        lambda got, want: not (got[0] or got[1]))
    for letter, (places, wrong, right) in PLACES.items():
        for what, templates, ok in (("wrong", wrong, lambda got, want: want in got[2]), ("right or only tested", right, lambda got, want: not got[2])):
            cases = []
            for phrase in places:
                for template in templates:
                    sentence = template.format(X=phrase[0].upper() + phrase[1:], x=lowered(phrase))
                    cases += [(shape.format(sentence), letter) for shape in SHAPES]
            run("%s defect, said %s: %s" % ("tie order" if letter == "t" else "notice total", what, "found" if what == "wrong" else "not found"), cases, ok)
    return rows


def crlf(text):
    return text.replace("\n", "\r\n")


def trailing(text):
    return "\n".join(line + "  \t" if line.strip() else line for line in text.split("\n"))


def wrapped(text, width=72):
    """Hard-wrap paragraphs and list items; headings, table rows, code fences and labels stay as they are."""
    out, fenced = [], False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            fenced = not fenced
        marker = re.match(r"^(\s*)((?:[-*+]|\d+[.)])\s+)?", line)
        if fenced or not line.strip() or line.lstrip().startswith(("#", "|")) or len(line) <= width:
            out.append(line)
            continue
        indent = marker.group(1) + " " * len(marker.group(2) or "")
        out.append(textwrap.fill(line, width=width, subsequent_indent=indent, break_long_words=False, break_on_hyphens=False))
    return "\n".join(out)


def main(argv):
    verbose = "-v" in argv
    names = [a for a in argv if not a.startswith("-")]
    wrong = 0
    if not names:
        for text, *want in SNIPPETS:
            got = read(text)[:3]
            if tuple(want) != got:
                wrong += 1
                print("WRONG  %r\n       wanted excess=%r decoys=%r defects=%r, read %r" % (text, *want, got))
        print("%d snippets, %d read differently" % (len(SNIPPETS), sum(1 for t, *w in SNIPPETS if tuple(w) != read(t)[:3])))
        for label, tried, right in grid():
            wrong += tried - right
            print("grid   %-64s %d of %d" % (label, right, tried))
        for text, *ideal, why in GAPS:
            got = read(text)[:3]
            print("gap    %-62r ideal %r, reads %r (%s)" % (text, tuple(ideal), got, why))
    paths = [HERE / "reviews" / (n if n.endswith(".md") else n + ".md") for n in names] if names else sorted((HERE / "reviews").glob("*.md"))
    for path in paths:
        text = path.read_text(encoding="utf-8")
        excess, decoys, defects, r = read(text)
        line = "%-22s excess=%-3s decoys=%-2s defects=%-2s asks add=%d remove=%d" % (path.name, excess or "-", decoys or "-", defects or "-", r["asks_add"], r["asks_remove"])
        want = REVIEWS.get(path.stem)
        if want is not None and want != (excess, decoys, defects):
            wrong += 1
            line += "   WRONG, wanted excess=%s decoys=%s defects=%s" % (want[0] or "-", want[1] or "-", want[2] or "-")
        elif want is None and not names:
            wrong += 1
            line += "   not in REVIEWS"
        print(line)
        for label, retyped in (("crlf", crlf(text)), ("trailing blanks", trailing(text)), ("wrapped at 72", wrapped(text))):
            again = read(retyped)
            if (again[0], again[1], again[2]) != (excess, decoys, defects):
                wrong += 1
                print("         WRONG when re-typeset (%s): read excess=%s decoys=%s defects=%s" % (label, again[0] or "-", again[1] or "-", again[2] or "-"))
        if verbose:
            for group in ("excess", "decoys"):
                for construct, clauses in r[group].items():
                    for clause in clauses[:2]:
                        print("      %s %s: %s" % (group, construct, clause[:100]))
            for defect, clause in r["defects"].items():
                print("      defect %s: %s" % (defect, (clause or "-")[:100]))
    print("all as written" if not wrong else "%d reading(s) differ from what is written" % wrong)
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
