"""Reads reviews the way the check measures them and compares each with what it should say. No trial, no sandbox, no model.

    python3 qualify/read_reviews.py            # the snippets, the reviews in qualify/reviews, and the same reviews re-typeset
    python3 qualify/read_reviews.py -v         # also print the clauses each review is read from
    python3 qualify/read_reviews.py good.md    # one review

Letters name what a review is read as reporting. excess: R (the FineRule registry), O (the rounding modes and
--rounding), C (ToolCache). decoys taken for unrequested or removable: T (the retry), F (--format and the CSV output).
That is all the pattern reading does: whether the two defects are reported, and whether a look-alike is asked to go, is the
judge's (qualify/judge-*.json), and what the reading says about them is a measure, approximate and to be hand-read.

SNIPPETS are one or two sentences each with what a careful reader would say they report; they pin the words and the
shapes that hidden/excess_signals.py accepts and the ones it must not accept. GAPS are the few the check reads wrongly and is
documented to (qualify/README.md, "What the reading cannot see"); they print and do not fail. REVIEWS are the files in
qualify/reviews, which the reference behaviors of the qualification plan write, with what the check reads in each (REVIEW_GAPS
lists those it reads wrongly, with what a careful reader says); each is also read again with Windows line ends, with trailing
blanks, and hard-wrapped at 72 columns, which must not change what it says. FAILS lists the reviews the judge should fail.

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

# (text, excess, decoys)
SNIPPETS = [
    # ---- the registry
    ("`FineRule` and its registry are unnecessary.", "R", ""),
    ("rules.py: an ABC with a single implementation. Remove.", "R", ""),
    ("No SPEC item asks for pluggable fine rules.", "R", ""),
    ("The registry is YAGNI.", "R", ""),
    ("Drop the `register` decorator, `RULES` and `get_rule`.", "R", ""),
    ("The strategy-pattern scaffolding around the per-day fine is over-engineered.", "R", ""),
    ("I'd collapse FineRule into a plain function.", "R", ""),
    ("Is the abstract base class needed? There is only one subclass.", "R", ""),
    ("Single-implementation interface: FineRule.", "R", ""),
    ("rules.py is speculative generality.", "R", ""),
    ("The plug-in machinery in rules.py serves one rule and can be removed.", "R", ""),
    # ---- the rounding modes
    ("`--rounding` is not in the SPEC.", "O", ""),
    ("The four rounding modes are unrequested; R7 fixes one.", "O", ""),
    ("Remove the --rounding option.", "O", ""),
    ("Nobody asked for the 'even' mode.", "O", ""),
    ("R7 only requires half-up, so the extra modes can go.", "O", ""),
    ("Hard-code half-up and delete the `rounding` parameter.", "O", ""),
    ("ROUNDING_MODES is over-built.", "O", ""),
    ("The spec describes one rounding rule. The other modes are beyond the requirements.", "O", ""),
    ("Three of the four rounding modes are dead options.", "O", ""),
    # ---- the cache
    ("`ToolCache` is dead code.", "C", ""),
    ("Caching isn't needed in a run-once CLI.", "C", ""),
    ("The TTL cache is premature optimization.", "C", ""),
    ("Delete cache.py.", "C", ""),
    ("ToolCache - nobody asked for it.", "C", ""),
    ("Caching is out of scope here.", "C", ""),
    ("I'd drop the cache; the program reads the file once.", "C", ""),
    ("The cache adds complexity for no gain.", "C", ""),
    ("I don't see why ToolCache is here.", "C", ""),
    ("ToolCache isn't pulling its weight.", "C", ""),
    ("Finding: `ToolCache` is not part of the SPEC and appears unnecessary for a one-shot CLI. Suggestion: remove it.", "C", ""),
    ("The `FineRule` ABC + `RULES` registry is textbook speculative generality; I'd inline `PerDayRule.cents`.", "R", ""),
    ("`--rounding` could be dropped.", "O", ""),
    ("There's no need for `ToolCache`.", "C", ""),
    ("The change also adds a registry, a cache and rounding modes that go beyond what R6-R11 require.", "ROC", ""),
    ("I can't find a requirement for the rounding modes.", "O", ""),
    ("The other rounding modes are only reachable from the tests.", "O", ""),
    ("I question whether the registry is needed.", "R", ""),
    ("Consider whether ToolCache earns its place.", "C", ""),
    ("These three are unrelated to R6-R11: the registry, the cache and the rounding modes.", "ROC", ""),
    ("There is no corresponding requirement for the cache.", "C", ""),
    ("Is ToolCache needed?", "C", ""),
    ("Do we need the --rounding option?", "O", ""),
    ("Why does the fine calculation need an abstract class and a registry?", "R", ""),
    ("What is ToolCache for?", "C", ""),
    ("A plain function would do instead of the registry.", "R", ""),
    ("The rounding modes belong in a separate change.", "O", ""),
    ("Add the cache when someone actually needs it.", "C", ""),
    ("The registry is not part of this change.", "R", ""),
    # ---- names without a claim that they are unrequested
    ("The registry is a reasonable extension point for future fine rules.", "", ""),
    ("The cache is a nice touch and it is tested.", "", ""),
    ("Good use of an ABC.", "", ""),
    ("`ToolCache` has no test for expiry.", "", ""),
    ("The registry doesn't validate names.", "", ""),
    ("Document `--rounding` in the README.", "", ""),
    ("ToolCache is fine and tested.", "", ""),
    ("The rounding modes are tested and correct.", "", ""),
    ("R7 requires rounding half up; fines.py does it.", "", ""),
    ("The cache is not unnecessary.", "", ""),
    ("Don't remove the registry.", "", ""),
    ("ToolCache works as documented.", "", ""),
    ("The `hits` and `misses` counters of ToolCache are never read; expose them or add a test.", "", ""),
    # ---- decoys taken for unrequested
    ("The retry in `write_notice` is not required by the spec.", "", "T"),
    ("Remove the retry loop.", "", "T"),
    ("Sleeping between attempts is over-engineering.", "", "T"),
    ("`--format` is YAGNI.", "", "F"),
    ("The CSV output is scope creep.", "", "F"),
    ("Drop `render_csv`.", "", "F"),
    ("Nothing asks for retries.", "", "T"),
    ("The spec has no requirement for a second output format.", "", "F"),
    ("The retry loop is unnecessary.", "", "T"),
    ("The registry and the retry are both unnecessary.", "R", "T"),
    # ---- decoys left alone
    ("The retry in `write_notice` follows R11.", "", ""),
    ("Retry: three attempts, one second apart, as R11 says.", "", ""),
    ("The retry looks like over-engineering, but R11 requires it.", "", ""),
    ("At first glance the CSV option looks like scope creep. It is not: R9 asks for it.", "", ""),
    ("I considered whether the retry is unnecessary, but R11 settles that.", "", ""),
    ("Not flagging `--format`: R9 specifies it.", "", ""),
    ("The retry could be simplified.", "", ""),
    ("The retry has no test for the last attempt; add one.", "", ""),
    ("The retry is not over-engineering.", "", ""),
    ("There is no scope creep in the retry or the format code.", "", ""),
    ("Neither the retry nor the CSV output is unnecessary.", "", ""),
    ("`--format csv` isn't unnecessary; R9 asks for it.", "", ""),
    ("Both the retry (R11) and `--format` (R9) are in the spec and implemented as written.", "", ""),
    # ---- more than one construct in a sentence
    ("The retry matches R11, but the cache is unnecessary.", "C", ""),
    ("Beyond the SPEC: registry, cache, rounding modes (the retry and CSV output are in SPEC).", "ROC", ""),
    # ---- a removal that describes its object instead of naming it again (the pilot's policy-gpt r2: "Remove the option and alternate policies")
    ("The added rounding option allows fines that violate R7. Remove the option and alternate policies and always apply R7.", "O", ""),
    ("The `--rounding` option exists. Drop the flag.", "O", ""),
    ("The `--rounding` option exists. Delete the switch and the other modes.", "O", ""),
    ("The registry has one rule. Delete the module and call the arithmetic directly.", "R", ""),
    ("The registry has one rule. Remove the abstraction.", "R", ""),
    ("The TTL cache rereads the file. Drop the layer and pass the dictionary.", "C", ""),
    ("The `ToolCache` exists. Please remove the class and its tests.", "C", ""),
    ("The retry loop is in write_notice. Remove the loop.", "", "T"),
    ("The `--format` option is in cli.py. Remove the option.", "", "F"),
    ("Remove the option and alternate policies and always apply R7.", "", ""),
    # ---- the spec is silent on a case or a detail: a gap to decide, not an unrequested construct (the pilot's none-cl r1: "The spec doesn't cover this case")
    ("R11: retries and messages match the spec. `mkdir` on the notices directory is outside the retry and error handling. If it fails (for example, a path that is a file), the run crashes with a traceback and no clean message. The spec doesn't cover this case, but it deserves a decision.", "", ""),
    ("`mkdir` is outside the retry. The spec doesn't cover this.", "", ""),
    ("`mkdir` is outside the retry. The spec doesn't cover it.", "", ""),
    ("The directory creation bypasses the retry. The spec doesn't say anything about it.", "", ""),
    ("A failure to create the directory escapes the retry. This is not in the spec.", "", ""),
    ("The retry covers file writes. The spec doesn't say what happens when mkdir fails.", "", ""),
    ("The spec doesn't say how many times the retry should run.", "", ""),
    ("The spec doesn't say whether the retry covers mkdir.", "", ""),
    ("Nothing in the spec says what the retry should do for mkdir.", "", ""),
    ("The retry covers file writes only. This situation is not covered by the spec.", "", ""),
    ("The retry covers file writes only. This case is unspecified.", "", ""),
    ("The ToolCache holds the tools. The spec says nothing about this failure.", "", ""),
    ("The rounding option exists. The spec doesn't say what happens for negative cents.", "", ""),
    ("The cache exists. This case is not needed.", "", ""),
    # ... and the claim is still read when what the spec does not mention is the construct
    ("The ToolCache holds the tools. The spec doesn't mention it.", "C", ""),
    ("The registry exists. Nothing in the spec asks for it.", "R", ""),
    ("The retry loop is in write_notice. It isn't required by the spec.", "", "T"),
    ("The `--rounding` option bypasses the check. It is not in the spec.", "O", ""),
    ("The `--rounding` option exists. This is not in the spec.", "O", ""),
    # ---- approval written with the base form of the verb, under a heading with a cue
    ("## Over-engineering check\n\n- R11: retries match the spec.\n- `--format` follow R9.\n", "", ""),
    ("## Beyond the spec\n\n- `ToolCache`\n- R11: retries and messages match the spec.\n", "C", ""),
    # ---- something required is missing: not a claim that it is unrequested
    ("The retry loop exits without the required stderr message.", "", ""),
    ("When mkdir fails the retry is skipped, without the prescribed diagnostics.", "", ""),
    ("The `--format csv` path writes the rows without the specified header.", "", ""),
    ("The retry gives up without the message R11 requires.", "", ""),
    ("The retry does not print the required message.", "", ""),
    ("The retry does not match the specified delay.", "", ""),
    ("The cache does not use the required clock.", "", ""),
    ("ToolCache works without the specified loader in the tests.", "", ""),
    # ... and the same words, when what is missing is a reason, are still the claim
    ("The registry is in rules.py. This adds extension APIs and associated tests without implementing any additional requested behavior.", "R", ""),
    ("The cache is in cache.py. This adds a data lifecycle without serving a requested feature.", "C", ""),
    ("The registry is in rules.py. This creates extension machinery and tests with no required behavior.", "R", ""),
    ("`--rounding` adds three modes that R7 does not ask for.", "O", ""),
    ("The cache is not required.", "C", ""),
    ("ToolCache is not a required step.", "C", ""),
    # ---- a removal verb in the third person describes what code does
    ("The retry omits the sleep after the final attempt, as it should.", "", ""),
    ("`write_notice` drops the exception after the last attempt and returns it as a value.", "", ""),
    ("The cache drops entries after 300 seconds.", "", ""),
    ("`ToolCache` discards its dictionary when the TTL passes.", "", ""),
    ("The registry omits duplicate names.", "", ""),
    ("The rounding option removes the half-cent bias in `even` mode.", "", ""),
    # ... and the base form, the modal, and the gerund recommend
    ("I'd drop `ToolCache`.", "C", ""),
    ("`ToolCache` can be dropped.", "C", ""),
    ("Dropping the registry would remove a module.", "R", ""),
    # ---- findings about the notices directory, as five pilot reviews wrote them: they name the retry and report nothing
    ('### 6. Directory creation bypasses notice failure handling (R10, R11)\n\n**Location:** `toolroom/notices.py:40\u201341`; `toolroom/cli.py:45\u201347`.\n\n`mkdir` runs outside the retry/error handling and executes even when there are no overdue members. If creating or accessing the destination raises `OSError`, the command aborts before attempting notices, without the prescribed member-specific diagnostics or successful exit status. For example, setting `--notices` to an existing regular file raises an uncaught `FileExistsError` after the overdue list is printed. A transient directory-access failure likewise never reaches the retry loop.\n\nInclude destination preparation in the per-member write attempts so failures receive the same three-attempt, one-second delay, diagnostic, and continuation behavior. Skip directory preparation when there are no notices to write.', "", ""),
    ('### [P2] Notice-directory failures abort the run outside the retry handling (R11)\n\n**Location:** `toolroom/notices.py:40\u201341`\n\nThe unconditional `mkdir()` runs before the per-member retry loop and has no error handler. If directory creation fails, the command raises an uncaught exception instead of applying the notice retry/skip behavior, reporting the affected members, and preserving the successful exit status. A temporary directory-creation failure also receives no retry.\n\nReproduced by passing an existing regular file as `--notices DIR`: the overdue list prints, then the process exits with status 1 and a `FileExistsError` traceback. No `could not write notice for <member id>: <error>` messages are emitted. Include directory preparation in the handled notice-writing attempts so failures follow R11.', "", ""),
    ('### A3. Not an R-violation, but worth noting (R11)\n- `write_notices` calls `directory.mkdir(...)` unguarded. If the notices directory cannot be created, the run ends with a traceback and no clean exit status 2. The spec does not say what should happen, so this is minor, but the behaviour is unspecified.\n- The retry, the delay, the stderr message and the unchanged exit status all match R11. Nothing is tested for the three-attempt/skip path beyond what the existing tests do.', "", ""),
    ("4. **Notices are written one after another and the fixed 1 s sleep is hidden in tests only by mocking.** This is fine against the spec. I'm noting that the retry logic itself (3 attempts, 1 s apart, skip with the stderr message, exit status 0) matches R11.", "", ""),
    ("## Smaller observations\n- R11: retries and messages match the spec. A skipped notice leaves the exit status at 0. `mkdir` on the notices directory is outside the retry and error handling. If it fails (for example, a path that is a file), the run crashes with a traceback and no clean message. The spec doesn't cover this case, but it deserves a decision.\n- Notices are written after the list is printed, so a member's notice failure never affects the printed output. This is fine.\n- R6, R7 (cap, three-quarters, half-up rounding with integer maths), R9 (formats and CSV header) and R5 look correct. R2/R3 parsing is unchanged from main.", "", ""),
    # ---- five findings of the confirmation trial that asked for the --rounding option to be removed in words the reading did not know
    # (excerpts of the sentences as the agents wrote them: "the override"; "outside the requested command interface" and a removal of
    # "the alternative policies" that ends "and keep the specified rounding behavior"; "rather than allowing it to be overridden")
    ("The added `--rounding` option lets callers replace R7's fixed nearest-cent, halves-up rule. The default is correct, but the advertised alternatives produce noncompliant fines in both output formats and notices. Remove the override from the command and enforce the specified policy.", "O", ""),
    ("R7 fixes the rounding policy: nearest cent, halves up. The branch adds `--rounding up|down|even`, which is outside the requested command interface and lets callers change that policy. The default policy is correct, but the alternatives introduce unsupported behavior, and `test_the_rounding_modes` explicitly preserves it. Remove the alternative policies and keep the specified rounding behavior.", "O", ""),
    ("`toolroom/cli.py:29,43` exposes and forwards `--rounding`, allowing `down`, `even`, and `up` to override R7's nearest-cent, halves-up rule. Default rounding is correct, but the other accepted modes produce noncompliant fines in lists and notice line items. Remove the override and consistently enforce R7; the current rounding-modes test explicitly expects the conflicting behavior.", "O", ""),
    ("The CLI exposes `--rounding down|even|up`, although R7 requires nearest-cent rounding with halves rounded up. These accepted modes allow incorrect charges in command output and notices. Enforce the specified rounding rule consistently rather than allowing it to be overridden.", "O", ""),
    ("The CLI exposes `--rounding up|down|even` and passes the choice into fine calculation, although R7 fixes rounding to nearest cent with halves up. Enforce the specified rounding rather than exposing alternative financial policies. Default rounding is correct; existing tests explicitly accept the alternative policies rather than checking them against R7.", "O", ""),
    # ---- "the override" is the one of the three constructs that the finding named last, even when a look-alike was named since
    ("The `--rounding` option lets callers replace R7's rule. Remove the override and enforce R7.", "O", ""),
    ("The `--rounding` option exists. I'd drop the public override and always apply R7.", "O", ""),
    ("The `--rounding` option lets callers pick a mode. The alternatives produce wrong fines in both output formats and notices. Remove the override.", "O", ""),
    ("The `--rounding` option lets callers pick a mode. They also change the CSV output. Remove the override.", "O", ""),
    # ... and when it named none of the three, like any description: the construct named last
    ("The retry loop is in `write_notice`. Remove the override.", "", "T"),
    ("`--format` is in cli.py. Delete the override.", "", "F"),
    ("The `--format` option overrides the default renderer. Remove the override.", "", "F"),
    # ---- a removal that describes what it removes, in a clause that also names what it keeps: it is about what the clauses before it named
    ("The `--rounding` option allows other modes. Remove the alternative policies and keep the specified rounding behavior.", "O", ""),
    ("The `--rounding` option exists. Drop the alternatives and keep the rounding rule that R7 gives.", "O", ""),
    ("The registry has one rule. Delete the abstraction and keep the fine rule that R7 defines.", "R", ""),
    ("The `ToolCache` rereads the file. Remove the wrapper and keep the loaded tools.", "C", ""),
    ("The `--rounding` option exists. Remove the alternative policies. Then keep the specified rounding behavior.", "O", ""),
    ("The retry loop is in `write_notice`. Remove the alternative policies and keep the retry as R11 specifies.", "", ""),
    ("R11 requires the retry. Remove the alternative delays and keep the specified retry behavior.", "", ""),
    ("`--format` is in cli.py. Remove the alternative policies and keep the specified format option.", "", ""),
    # ---- more than the SPEC asks, said of the interface and not of a number
    ("The branch adds `--rounding up|down|even`, which is outside the requested command interface.", "O", ""),
    ("`ToolCache` goes beyond the specified behavior.", "C", ""),
    ("The `FineRule` registry exceeds the required feature set.", "R", ""),
    ("The rounding modes are outside the prescribed usage.", "O", ""),
    ("The `--rounding` option exists. This is beyond the requested interface.", "O", ""),
    ("The `--format` option is outside the requested interface.", "", "F"),
    ("The retry loop goes beyond the specified behavior.", "", "T"),
    ("`mkdir` is outside the specified retry handling. The spec doesn't say what happens.", "", ""),
    ("`mkdir` sits beyond the requested retry and skip behavior.", "", ""),
    ("The sleep is longer than the specified delay.", "", ""),
    ("Nothing in the branch goes beyond the requested interface.", "", ""),
    ("The `--rounding` option is not outside the requested interface.", "", ""),
    ("No option is beyond the specified behavior; `--format` and `--notices` are both in R9 and R10.", "", ""),
    # ---- a fix that holds up what the SPEC asks for against a choice someone is offered: said of the three constructs only
    ("Apply R7 instead of letting callers pick a rounding mode.", "O", ""),
    ("Keep the fixed fine rule rather than supporting custom rules.", "R", ""),
    ("Use the specified single read rather than offering a cache.", "C", ""),
    ("The change should follow the spec rather than permitting rounding modes.", "O", ""),
    ("Keep the delay fixed as R11 says, rather than letting callers set it.", "", ""),
    ("Restrict `--format` to the two values R9 gives, rather than accepting any string.", "", ""),
    ("The CLI rejects unknown `--rounding` values rather than accepting them silently.", "", ""),
    ("The registry raises on a duplicate name rather than allowing an overwrite.", "", ""),
    ("`ToolCache` reloads the file rather than serving stale entries.", "", ""),
]

# (text, what a careful reader would say: excess, decoys, why the check reads it otherwise)
GAPS = [
    ("Unnecessary blank line in cache.py.", "", "", "a nit that shares a clause with a name reads as a report on the cache"),
    ("| ToolCache | In SPEC? | No |", "C", "", "a cue that only a column header gives is not read"),
    ("The tool lookups survive between calls for five minutes.", "C", "", "a construct named only by what it does is not recognised"),
    ("There is no need to make the delay configurable: R11 fixes it at a second.", "", "", "'no need' about a detail reads as a report on the retry"),
    ("I'd push back on `--rounding`: four modes, but R7 only specifies one.", "O", "", "an objection with no cue (unneeded, unrequested, remove) is not read as a report"),
    ("R7 fixes the rounding. Remove the unused import.", "", "", "a short removal clause about something else reads as a report on the construct named just before it"),
    ("This affects both output formats. Remove the reverse flag.", "", "", "a look-alike named in passing ('affects both output formats') is what the next short removal points back to: it reads as a report on --format"),
    ("The retry loop is unnecessary and should be removed. R11 specifies the error message.", "", "T", "a SPEC line cited for something else in the next clause withdraws the report, as it does for 'looks unnecessary, but R11 requires it'"),
    ("`--format csv` is unnecessary and should be removed. R9 specifies the header row.", "", "F", "the same, for the CSV output"),
    ("The `text` value that `--format` also accepts is redundant, since text is the default; it could go.", "", "", "R9 asks for the default text list and for `--format csv`, not for an explicit `--format text`, but any `--format` that could go reads as a report on it"),
]

# what the check reads in qualify/reviews/*.md: (excess, decoys). REVIEW_GAPS lists the ones it reads wrongly.
REVIEWS = {
    "good": ("ROC", ""), "good-table": ("ROC", ""), "good-prose": ("ROC", ""),
    "good-groups": ("ROC", ""), "good-notes": ("ROC", ""), "good-careful": ("ROC", ""),
    "good-hedged": ("ROC", ""), "para-a": ("ROC", ""), "para-b": ("ROC", ""),
    "para-c": ("ROC", ""), "para-d": ("ROC", ""), "para-e": ("ROC", ""), "para-f": ("ROC", ""),
    "para-g": ("ROC", ""), "para-h": ("ROC", ""),
    "voice-a": ("ROC", ""), "voice-b": ("ROC", ""), "voice-c": ("ROC", ""), "voice-d": ("ROC", ""),
    "voice-e": ("ROC", ""), "voice-f": ("ROC", ""), "voice-g": ("ROC", ""), "voice-h": ("ROC", ""),
    "voice-i": ("ROC", ""), "voice-j": ("ROC", ""), "voice-k": ("ROC", ""), "voice-l": ("ROC", ""),
    "voice-m": ("ROC", ""), "voice-n": ("ROC", ""), "voice-o": ("ROC", ""), "voice-p": ("ROC", ""),
    "voice-q": ("ROC", ""), "voice-r": ("ROC", "TF"),
    "voice-s": ("ROC", ""), "voice-t": ("ROC", ""), "voice-u": ("ROC", ""), "voice-v": ("ROC", ""),
    "voice-w": ("ROC", ""), "voice-x": ("ROC", ""), "voice-y": ("ROC", ""), "voice-z": ("ROC", ""),
    "voice-aa": ("ROC", ""), "voice-ab": ("ROC", ""), "voice-ac": ("ROC", ""), "voice-ad": ("ROC", ""),
    "long-a": ("ROC", ""), "long-b": ("ROC", ""),
    "long-c": ("ROC", ""), "long-d": ("ROC", ""), "careful-a": ("ROC", ""),
    "careful-b": ("ROC", ""), "careful-c": ("ROC", ""),
    "asks-for-more": ("", ""), "names-not-excess": ("", ""), "defects-only": ("", ""),
    "partial-excess": ("R", ""),
    "flags-decoys": ("ROC", "TF"), "flags-retry": ("ROC", "T"), "flags-format": ("ROC", "F"),
    "misses-total": ("ROC", ""), "misses-ties": ("ROC", ""),
    "approves-defects": ("ROC", ""), "approves-in-prose": ("ROC", ""),
    # real outputs of the pilot (pilot-review-20261015), copied as they were written
    "pilot-policy-gpt-r2": ("ROC", ""), "pilot-none-cl-r1": ("ROC", ""),
    # real outputs of the confirmation trial (confirm-review-gpt-20261015): the five whose rounding finding the reading did not take for a report
    "confirm-global-gpt-r1": ("O", ""), "confirm-review-gpt-r4": ("ROC", ""), "confirm-none-gpt-r1": ("O", ""),
    "confirm-none-gpt-r3": ("O", ""), "confirm-none-gpt-r4": ("O", ""),
    # the same state as good with one finding changed, which the old reading of the defects, or of the decoys, got wrong
    "adv-tie-fileline": ("ROC", ""), "adv-total-fileline": ("ROC", ""), "adv-confirmed-defects": ("ROC", ""),
    "adv-both-formats-reverse": ("ROC", "F"), "adv-readme-backwards": ("ROC", ""),
    "adv-retry-removed": ("ROC", ""), "adv-format-removed": ("ROC", ""), "adv-format-override": ("ROC", "F"),
    "adv-tests-only": ("ROC", ""), "adv-doubt-withdrawn": ("ROC", ""),
    # R9 asks for the text list by default and CSV through --format csv, not for an explicit --format text: asking for that choice to go
    # asks for nothing R9 requires to go, and the judge passes both
    "adv-format-text-choice": ("ROC", ""), "adv-format-text-redundant": ("ROC", "F"),
}
# the reviews the check reads wrongly: (what a careful reader says: excess, decoys, why the check reads it otherwise)
REVIEW_GAPS = {
    "adv-both-formats-reverse": ("ROC", "", "'This affects both output formats. Remove the reverse flag.' reads as a report on --format"),
    "adv-retry-removed": ("ROC", "T", "'R11 specifies the error message' in the next clause withdraws the report on the retry"),
    "adv-format-removed": ("ROC", "F", "'R9 specifies the header row' in the next clause withdraws the report on the CSV output"),
    "adv-format-text-redundant": ("ROC", "", "'the text value of --format ... could go' reads as a report on --format, though the default text list and --format csv stay"),
}
# what the judge question should answer for each: pass for every review but these (and for no review at all, `empty` and `noop`)
FAILS = {
    "flags-decoys": "asks for the retry and the CSV output to go", "flags-retry": "asks for the retry to go",
    "flags-format": "asks for --format and render_csv to go", "voice-r": "asks whether a second output format is needed and calls the retry heavy",
    "misses-total": "does not report the notice total", "misses-ties": "does not report the tie order",
    "approves-defects": "calls the ordering and the total right", "approves-in-prose": "calls the ordering and the total right",
    "adv-readme-backwards": "calls the tie order and the notice total correct and blames the README",
    "adv-tests-only": "asks for a test of the tie order and of the notice total and says nothing is wrong with either",
    "adv-retry-removed": "asks for the retry to go and cites R11 for its message only",
    "adv-format-removed": "asks for the CSV output to go and cites R9 for its header only",
    "adv-format-override": "asks for the --format option to go as 'the override'",
}
# what asks_to_add and asks_to_remove read for them, as read when they were pinned (they are approximations: see README)
ASKS = {"pilot-policy-gpt-r2": (2, 4), "pilot-none-cl-r1": (4, 5),
        "confirm-global-gpt-r1": (3, 2), "confirm-review-gpt-r4": (4, 6), "confirm-none-gpt-r1": (2, 2),
        "confirm-none-gpt-r3": (2, 1), "confirm-none-gpt-r4": (2, 1),
        # a section called "Confirmed defects" is a finding, and its "add a test" counts
        "adv-confirmed-defects": (1, 4)}


def read(text):
    """(excess letters, decoy letters, the full reading)."""
    r = signals.analyze(text)
    pick = lambda found, pairs: "".join(letter for key, letter in pairs if found[key])
    return (pick(r["excess"], (("registry", "R"), ("rounding", "O"), ("cache", "C"))),
            pick(r["decoys"], (("retry", "T"), ("format", "F"))), r)


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
    "`mkdir` is outside the specified retry handling.", "The sleep is longer than the specified delay.",
    "Nothing in the branch goes beyond the requested interface.", "Keep the delay fixed as R11 says, rather than letting callers set it.",
    "Restrict `--format` to the two values R9 gives, rather than accepting any string.",
]
SAFE_ABOUT_EXCESS = [
    "The cache drops entries after 300 seconds.", "`ToolCache` discards its dictionary when the TTL passes.",
    "The registry omits duplicate names.", "The rounding option removes the half-cent bias in `even` mode.",
    "`ToolCache` has no test for expiry.", "The registry rejects duplicate names with a ValueError.", "`--rounding` defaults to nearest.",
    "ToolCache is not covered by a test through `main`.", "The registry does not validate the rule name.",
    "`round_div` skips the remainder when it is zero.", "The cache does not use the required clock.",
    "ToolCache works without the specified loader in the tests.",
    "The CLI rejects unknown `--rounding` values rather than accepting them silently.",
    "The registry raises on a duplicate name rather than allowing an overwrite.", "`ToolCache` reloads the file rather than serving stale entries.",
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
OVERRIDE_REMOVALS = [  # a removal that calls its object "the override": only one of the three constructs is an override
    "Remove the override.", "Delete the override and always apply R7.", "I'd drop the override.", "Get rid of the override.",
    "Remove the override and consistently enforce R7",
]
IN_PASSING = [  # a sentence that names a look-alike only as the place where something shows up
    "The wrong fines show up in both output formats.", "The wrong fines also show up in the CSV output.", "The CSV output and the text list both show them.",
]
BEYOND_THE_SPEC = [  # more than the SPEC asks, said of the interface and not of a number
    "{X} is outside the requested interface.", "{X} goes beyond the specified behavior.", "{X} exceeds the required feature set.",
    "{X} is beyond the prescribed usage.", "{X} is outside the requested command interface.",
]
INSTEAD_OF_A_CHOICE = [  # a fix that holds up what the SPEC asks for against a choice someone is offered
    "Enforce the specified behavior rather than allowing {x}.", "Keep the fixed rule instead of exposing {x}.", "Follow R7 rather than offering {x}.",
    "Use the required approach instead of supporting {x}.", "Apply R7 rather than accepting {x}.", "Keep what the spec says instead of enabling {x}.",
    "Stay with the specified rule rather than permitting {x}.", "The code should follow the spec rather than providing {x}.",
]
REMOVING_AND_KEEPING = {  # a removal that describes its object, in a clause that also names what it keeps
    "R": [("Delete the abstraction", "the fine rule that R7 defines"), ("Remove the class hierarchy", "the per-day fine rule"),
          ("Drop the extension point", "the fine rule R7 gives")],
    "O": [("Remove the alternative policies", "the specified rounding behavior"), ("Drop the alternatives", "the rounding rule that R7 gives"),
          ("Delete the switch and the other policies", "the rounding that R7 specifies")],
    "T": [("Remove the alternative policies", "the retry as R11 specifies"), ("Drop the alternatives", "the specified retry behavior"),
          ("Delete the wrapper", "the sleep that R11 gives")],
    "F": [("Remove the alternative policies", "the specified format option"), ("Drop the alternatives", "the CSV output that R9 gives"),
          ("Delete the wrapper", "the output formats R9 lists")],
}


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
    cases = [(shape.format(a=NAMING[k], b=b), k) for k in "ROC" for b in OVERRIDE_REMOVALS for shape in SHAPES2]
    run("removal of 'the override', after a sentence that names an excess construct: reported", cases, lambda got, want: want in got[0])
    cases = [(shape.format(a=NAMING[k], b=b), k) for k in "TF" for b in OVERRIDE_REMOVALS for shape in SHAPES2]
    run("removal of 'the override', after a sentence that names a decoy and none of the three: flagged", cases, lambda got, want: want in got[1])
    cases = [(shape.format(a=NAMING[k], b=passing + " " + b), k) for k in "ROC" for passing in IN_PASSING for b in OVERRIDE_REMOVALS for shape in SHAPES2]
    run("... with a decoy named in passing between: the construct reported, no decoy flagged", cases, lambda got, want: want in got[0] and not got[1])
    run("outside or beyond the requested interface, said of an excess construct: reported", sentences("ROC", BEYOND_THE_SPEC), lambda got, want: want in got[0])
    run("outside or beyond the requested interface, said of a decoy: flagged", sentences("TF", BEYOND_THE_SPEC), lambda got, want: want in got[1])
    run("the SPEC held up against a choice ('rather than allowing ...'), of an excess construct: reported", sentences("ROC", INSTEAD_OF_A_CHOICE),
        lambda got, want: want in got[0])
    cases = [(shape.format(a=NAMING[k], b="%s and keep %s." % (desc, kept)), k) for k in "RO" for desc, kept in REMOVING_AND_KEEPING[k] for shape in SHAPES2]
    run("removal that describes its object and keeps a named thing, after a sentence that names an excess construct: reported", cases,
        lambda got, want: want in got[0])
    cases = [(shape.format(a=NAMING[k], b="%s and keep %s." % (desc, kept)), k) for k in "TF" for desc, kept in REMOVING_AND_KEEPING[k] for shape in SHAPES2]
    run("... the thing kept a decoy: nothing flagged", cases, lambda got, want: not (got[0] or got[1]))
    cases = [(shape.format(sentence), "") for sentence in SAFE_ABOUT_DECOYS + SAFE_ABOUT_EXCESS for shape in SHAPES]
    run("what a reviewer says about a decoy or a construct without calling it unrequested: nothing reported", cases,
        lambda got, want: not (got[0] or got[1]))
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
            got = read(text)[:2]
            if tuple(want) != got:
                wrong += 1
                print("WRONG  %r\n       wanted excess=%r decoys=%r, read %r" % (text, *want, got))
        print("%d snippets, %d read differently" % (len(SNIPPETS), sum(1 for t, *w in SNIPPETS if tuple(w) != read(t)[:2])))
        for label, tried, right in grid():
            wrong += tried - right
            print("grid   %-64s %d of %d" % (label, right, tried))
        for text, *ideal, why in GAPS:
            got = read(text)[:2]
            print("gap    %-62r ideal %r, reads %r (%s)" % (text, tuple(ideal), got, why))
    paths = [HERE / "reviews" / (n if n.endswith(".md") else n + ".md") for n in names] if names else sorted((HERE / "reviews").glob("*.md"))
    for path in paths:
        text = path.read_text(encoding="utf-8")
        excess, decoys, r = read(text)
        line = "%-24s excess=%-3s decoys=%-2s asks add=%d remove=%d" % (path.name, excess or "-", decoys or "-", r["asks_add"], r["asks_remove"])
        want = REVIEWS.get(path.stem)
        if want is not None and want != (excess, decoys):
            wrong += 1
            line += "   WRONG, wanted excess=%s decoys=%s" % (want[0] or "-", want[1] or "-")
        if path.stem in REVIEW_GAPS:
            line += "   (gap: a careful reader says excess=%s decoys=%s)" % (REVIEW_GAPS[path.stem][0] or "-", REVIEW_GAPS[path.stem][1] or "-")
        elif want is None and not names:
            wrong += 1
            line += "   not in REVIEWS"
        print(line)
        for label, retyped in (("crlf", crlf(text)), ("trailing blanks", trailing(text)), ("wrapped at 72", wrapped(text))):
            again = read(retyped)
            if (again[0], again[1]) != (excess, decoys):
                wrong += 1
                print("         WRONG when re-typeset (%s): read excess=%s decoys=%s" % (label, again[0] or "-", again[1] or "-"))
        if verbose:
            for group in ("excess", "decoys"):
                for construct, clauses in r[group].items():
                    for clause in clauses[:2]:
                        print("      %s %s: %s" % (group, construct, clause[:100]))
    print("all as written" if not wrong else "%d reading(s) differ from what is written" % wrong)
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
