"""What a review of the toolroom branch says about its three unrequested constructs and its two decoys, and what it asks for.

review-flags-excess hands a reviewer a change with two defects against SPEC.md, three constructs no requirement asks
for, and two look-alikes that SPEC.md does require. Whether the review reports the two defects, and whether it asks for a
look-alike to go, decides the run, and a judge decides that (scenario.json, check.py's judge_context). This module only
measures, by name and cue, and only approximately: it reads the review the reviewer wrote (review_text.py splits it into
blocks and clauses) and says, for each of the three constructs, whether the review reports it as unrequested, unneeded, or
removable, which look-alike it seems to flag, and how many findings ask to add and to remove. Read the reviews themselves
in any trial that decides on one of these (qualify/README.md, "What the reading cannot see").

Excess (registry, rounding, cache) and decoys (retry, format). A clause that names the construct, by identifier or by
what it is called, and carries a cue that it is unrequested, unneeded, or removable, reports it. A cue is
- strong: unrequested, unnecessary, speculative, YAGNI, over-engineered, scope creep, "not required", "no requirement",
  "the spec does not ask for", "nothing needs it", "only one implementation", "adds complexity for no benefit", ...;
- strict removal: remove, delete, drop, inline, strip, "get rid of", "can go", "removable", ..., bound to what it acts
  on: names after the verb ("remove X and Y"), names before it after modal words ("X can be removed", "X is
  removable") or a bare colon ("X: delete"), and every name of a table row that has a verdict such as Remove;
- soft removal (excess only): simplify, collapse, hard-code, "replace with a plain ...".
Two more cues, said of the interface and of a choice:
- beyond the interface: "outside the requested command interface", "beyond the specified behavior", "exceeds the required
  feature set"; not a number ("the sleep is longer than the specified delay");
- a choice held up against the SPEC (excess only): a clause that mentions the SPEC and says "rather than" or "instead of"
  allowing, permitting, exposing, offering, supporting, providing, accepting, enabling, or letting ("enforce the specified
  rounding rule rather than allowing it to be overridden"). Said of the retry or --format ("keep the delay fixed as R11 says,
  rather than letting callers set it") it asks for something else and reports nothing; without the SPEC ("rejects unknown
  modes rather than accepting them") it is praise.
A cue turned round by a negator within five words ("not unnecessary", "don't remove") counts for nothing. A clause
without a name that carries a cue and points back reports what the clauses before it named. It points back when it
says "it", "they", "all three", or "this" or "that" (but not "this case", "that failure", or another word for a
circumstance), describes the construct without naming it ("remove the option and alternate policies", "delete the
module"), is a few words about nothing else, or is nothing but the cue ("remove it", "YAGNI"). A removal that describes
what it removes in a clause that also names what it keeps ("remove the alternative policies and keep the specified rounding
behavior") points back too, and the name it keeps is not what it removes (a look-alike it keeps is never reported by it).
"The override" is about the one of the three constructs that the finding named last, even when a look-alike was named since
("... in both output formats and notices. Remove the override."), and, when it named none, about whatever it named last ("The
--format option overrides the default renderer. Remove the override.").
Four kinds of clause are not reports on a construct they sit beside:
- a statement that the SPEC is silent on a detail or a case ("the spec doesn't say what happens when mkdir fails", "the spec
  doesn't cover this case", "nothing in the spec says whether ..."), which asks for something to be decided;
- a statement that something required is missing ("exits without the required stderr message", "does not print the
  specified header", "gives up without the message R11 requires"), which is a defect or a gap; "adds a layer without
  implementing any requested behavior" and "with no required behavior" still say that nothing asked for it;
- a removal verb in the third person ("the cache drops entries", "the retry omits the sleep after the last attempt",
  "this discards the cap"), which describes code; the base form, the gerund, and the modal recommend ("drop it", "dropping
  the cache", "can be dropped");
- a clause that uses the construct only as a reference point ("mkdir is outside the retry", "the directory bypasses the
  retry"): it is not about the construct, so a cue in that clause, or a "this" after it, is not about the construct either.
Pilot reviews of this branch write these: ten of twelve report the notices directory, which is created outside the retry,
five of them with the retry as the object of "outside" or "bypass", and eight say the spec is silent on something.
A heading or a lead-in ("Beyond the spec:") reports what is named under it, unless the item approves of itself.
For a decoy the report is withdrawn when the same clause approves ("R11 requires it", "matches R9", "fine"), or one of
the next two clauses approves or cites the SPEC line without a cue ("...but R11 settles that"): a reviewer who read the
SPEC found the requirement. For an excess construct approval does not cancel a cue in its own clause, because the SPEC
requires none of the three and the words of approval in such a clause are about something else ("R7 asks for
half-up, but --rounding offers four modes").

Asks. A finding (a heading section, a list item, a table row, or a line of a paragraph written one finding to a line;
not a summary) asks to add something when a clause of it, or of the headings above it, says so ("add", "should
validate", "missing", "no tests", "untested", "does not check", ...) and asks to remove something when a clause carries
a cue of the kinds above, unless that clause is the fix of a defect ("drop `reverse=True`"). Asks count every cue, the
four kinds of clause above included, and a summary paragraph under the title, so a finding that says "the spec does not say
what should happen" counts as asking to remove something (see qualify/README.md). A review that reports a construct has
asked for something to be removed, whatever the count says (check.py: asks_only_for_more).

What it cannot see is in qualify/README.md: a construct named only by what it does, a cue that is only implied
("In SPEC? No"), and a nit that shares a clause with a name ("unnecessary blank line in cache.py").
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_text as rt  # noqa: E402


def rx(*parts):
    return re.compile("|".join("(?:%s)" % p for p in parts), re.I)


# ---- what is named ---------------------------------------------------------------------------------------------

EXCESS = {
    "registry": rx(
        r"\bfine[- ]?rules?\b", r"\bperdayrule\b", r"\bget_rule\b", r"\brules\.py\b", r"\bregister(?:ed|s|ing)?\b",
        r"\bregistr(?:y|ies|ation)\b", r"\bplug-?ins?\b", r"\bpluggab\w+", r"\bextension[- ]points?\b", r"\babstract\b",
        r"\babc\b", r"\bbase[- ]class(?:es)?\b", r"\bsubclass(?:es)?\b", r"\bstrateg(?:y|ies)\b", r"\bcustom rules?\b",
        r"\brule (?:class|classes|hierarchy|abstraction|framework|mechanism|system|interface|lookup)\b"),
    "rounding": rx(
        r"--rounding\b", r"\brounding\b", r"\bround_div\b", r"\bROUNDING_MODES\b", r"\bmodes?\b", r"\bhalf[- ]?even\b", r"\bbankers?\b"),
    "cache": rx(
        r"\btoolcache\b", r"\bcache\.py\b", r"\bcach(?:e|es|ed|ing)\b", r"\bttl\b", r"\btime[- ]to[- ]live\b",
        r"\bmemoi[sz]\w*", r"\bhit\s*/\s*miss", r"\bhits\b", r"\bexpir(?:y|es|ing|ation)\b"),
}
# decoy: (what it is called, the SPEC line that requires it)
DECOYS = {
    "retry": (rx(
        r"\bretr(?:y|ies|ied|ying)\b", r"\bre-?attempts?\b", r"\battempts?\b", r"\bback-?off\b", r"\bsleep\w*",
        r"\bdelay\b"), "R11"),
    "format": (rx(
        r"--format\b", r"\brender_csv\b", r"\brender_text\b",
        r"\bcsv (?:output|format|renderer|rendering|writer|export|option|mode|support)\b",
        r"\b(?:text|output|report|list)\s*/\s*csv\b", r"\bcsv\s*/\s*text\b", r"\boutput formats?\b",
        r"\bformat (?:option|flag|switch|argument|choice|selector|parameter)\b", r"\btext and csv\b",
        r"\bcsv and text\b"), "R9"),
}
SOURCES = list(EXCESS.items()) + [(name, found[0]) for name, found in DECOYS.items()]


def names(clause):
    """{construct: [(start, end)]} for every construct a clause names."""
    found = {}
    for construct, pattern in SOURCES:
        spots = [(m.start(), m.end()) for m in pattern.finditer(clause)]
        if spots:
            found[construct] = spots
    return found


def rule_of(construct):
    """The SPEC line that requires a construct, or None for the three that no line asks for."""
    return DECOYS[construct][1] if construct in DECOYS else None


# ---- cues ------------------------------------------------------------------------------------------------------

STRONG = rx(  # a negator turns these round
    r"\bun(?:requested|needed|necessary|necessarily|required|specified|warranted|justified|asked|called[- ]for)\b",
    r"\b(?:needless(?:ly)?|superfluous|gratuitous(?:ly)?|extraneous|surplus|redundant|pointless|overkill|unused|cruft|bloat\w*)\b",
    r"\bdead (?:code|weight|options?|modes?|flags?|knobs?|switch(?:es)?|paths?|branch(?:es)?|settings?|parameters?)\b",
    r"\bover[- ]?(?:engineer\w*|built|build\w*|design\w*|abstract\w*|general\w*|complicat\w*|specif\w*)\b",
    r"\bpremature(?:ly)? (?:abstract\w*|generali[sz]\w*|optimi[sz]\w*|flexib\w*)",
    r"\b(?:speculative|speculation|yagni|gold[- ]?plat\w*|scope[- ]?creep|feature[- ]?creep|creeping scope)\b",
    r"\b(?:extra|additional|surplus)\s+(?:\w+\s+)?(?:machinery|complexity|abstraction|layers?|knobs?|modes?|options?|settings?|features?|surface|indirection|code|infrastructure|plumbing|flexibility|configurability|generality)\b",
    r"\b(?:more|bigger)\s+(?:machinery|complexity|abstraction|flexibility|generality)\s+than\b",
    r"\bmore than (?:the )?(?:spec|specification|requirements?|is (?:needed|required|necessary)|needed|required|necessary)\b",
    r"\b(?:beyond|outside|exceeds?|exceeding|goes beyond|going beyond|over and above)\s+(?:\w+\s+){0,2}?(?:the\s+)?(?:spec|specification|requirements?|scope|brief)\b",
    r"\bout[- ]of[- ]scope\b",
    r"\b(?:adds?|introduces?|brings?|carries|costs?)\s+(?:\w+\s+){0,3}?(?:complexity|indirection|machinery|surface area|moving parts|maintenance)\b",
    r"\b(?:only|just)\s+(?:one|a single|1|a lone)\s+(?:\w+\s+)?(?:implementation|impl\w*|subclass|concrete|rule|backend|strategy)\b",
    r"\b(?:single|sole|lone|one|1)[\s-]+(?:concrete\s+)?(?:implementation|impl\w*|subclass)\b",
    r"\b(?:heavy|heavyweight|heavy-handed|too (?:much|heavy|complex|complicated|elaborate|fancy)) for\b",
    r"\bsolution (?:looking|in search) (?:for|of) a problem\b",
    r"\b(?:can|could|should|may|might|ought to) (?:simply |just |safely |probably |all )*go\b", r"\bcandidates? for (?:removal|deletion|removing|deleting|dropping)\b",
    r"\bbeyond what\b[^.;|]{0,40}?\b(?:require\w*|ask\w*|specif\w*|need\w*)\b",
    r"\bmore than\b[^.;|]{0,30}?\b(?:requires?|asks? for|specif(?:y|ies)|needs?)\b",
    r"\bunrelated to\b[^.;|]{0,30}?\b(?:r\d|spec|requirements?)\b",
    r"\bonly\s+(?:reachable|used|called|exercised|referenced|exposed)\s+(?:from|by|in|through)\s+(?:the\s+)?tests?\b",
    r"\bconsider whether\b[^.;|]{0,60}?\b(?:needed|necessary|earns?|worth|warranted|justified)\b",
    r"\b(?:question|doubt|wonder|unsure|unclear)\b[^.;|]{0,60}?\b(?:needed|necessary|worth|earns?|warranted|justified|benefit)\b",
    r"\b(?:plain|simple|direct)\s+(?:function|constant|literal|call|computation|value)\s+(?:would|will|could|should)\s+(?:do|suffice|be enough|be sufficient)\b",
    r"\b(?:suffices?|is enough|are enough|is sufficient|are sufficient)\b[^.;|]{0,20}$",
    r"\b(?:belongs?|better|should be|could be|can be)\s+(?:in\s+)?(?:a\s+|its own\s+|another\s+|the next\s+)?(?:separate|different|follow-?up|own)\s+(?:change|pr|pull request|ticket|commit|patch|story|issue|branch)\b",
    r"\b(?:until|when|if)\s+(?:someone|anyone|somebody|a caller|a consumer|there is a (?:caller|need|use))\s+(?:actually\s+)?(?:needs?|asks?|wants?|appears?)\b",
    r"\b(?:defer|postpone)\w*\b[^.;|]{0,30}$",
    r"\b(?:could|can|should|would)\s+(?:simply |just |easily |safely )?be\s+(?:a|an|just a|replaced (?:by|with) a)\s+(?:plain |simple |single |direct )?(?:function|constant|literal|call|value|one-liner)\b",
    r"\btoo many\s+(?:moving parts|layers|knobs|options|abstractions|indirections|concepts|files|modules)\b",
    r"\b(?:heavier|bigger|larger|more complex|more complicated|more elaborate|fancier|longer)\s+than\s+(?:it\s+)?(?:needs?|has|ought|should|is needed|necessary)\b",
    r"\b(?:a|one)\s+single\s+(?:attempt|try|write|call)\b[^.;|]{0,40}\b(?:would|will|should|could)\s+(?:do|suffice|be enough)\b",
)
SELF = rx(  # already negative: the SPEC does not ask for it, nothing uses it, it earns nothing
    r"(?:\bnot|n't)\s+(?:\w+\s+){0,4}?(?<!the )(?<!its )(?<!their )(?<!this )(?<!that )(?<!these )(?<!those )(?:required|requested|asked|ask|asks|needed|needs?|called|mandated|demanded|necessary|warranted|justified|wanted|wants?)\b",
    r"(?:\bnot|n't|\bnever|\bnowhere|\bno)\s+(?:\w+\s+){0,3}?(?:in|by|part of|covered (?:in|by)|mentioned (?:in|by)|specified (?:in|by)|described (?:in|by)|stated (?:in|by)|found in|backed by|supported by|grounded in|justified by|traceable to|tied to|requested (?:in|by)|required (?:in|by)|asked for (?:in|by))\s+(?:the |any |a |this )?(?:spec|specification|requirements?|spec\.md|r\d+|requirement lines?)\b",
    r"\b(?:buys?|gains?|gives?|adds?|provides?|offers?|brings?)\s+(?:us\s+)?(?:nothing|no (?:value|benefit|use|purpose))\b",
    r"(?:spec|specification|requirements?|spec\.md|\br\d+)\b[^.;|]{0,40}?\b(?:does(?:n't|\s+not)|do(?:es)?n't|never|nowhere)\b[^.;|]{0,25}?\b(?:ask|require|call|mention|specify|say|describe|state|cover|need|demand|mandate|want|define)",
    r"\b(?:nothing|none|no one|nobody)\s+(?:(?:in|of|anywhere in|else in|within)\s+(?:the\s+)?(?:[\w#-]+\s+){0,3}?)?(?:requires?|requests?|requested|asks?|asked|calls?|called|mentions?|mentioned|specif(?:y|ies)|says?|describes?|needs?|needed|demands?|mandates?|uses?|used|wants?|wanted|registers?|plugs?|implements?|subclasses|selects?|switches|chooses|picks|sets?|passes|varies|changes)\b",
    r"\bno (?:requirement|spec line|spec item|line|item|r\d+|r#|r-number|caller|callers|code|consumer|user)\b[^.;|]{0,50}?\b(?:requires?|requests?|asks?|calls?|mentions?|specif(?:y|ies)|says?|describes?|needs?|demands?|mandates?|uses?|wants?)\b",
    r"(?:\bnot|n't)\s+(?:\w+\s+){0,8}?(?:earns?|justif(?:y|ies)|worth|pull\w*)\b",
    r"\b(?:don't|do not|can't|cannot)\s+see\s+(?:why|what|the\s+(?:point|need|use|reason|value))\b",
    r"\bfor (?:a |just |only )?(?:single|one|1) (?:rule|implementation|impl\w*|backend|strategy|use|case|caller|format)\b",
    r"\b(?:spec|specification|requirements?)\s+(?:is\s+)?(?:silent|mute)\b", r"\bsays nothing about\b",
    r"\bno (?:\w+\s+){0,2}?(?:requirement|spec line|basis|justification|need|reason|benefit|value|purpose|point)\b",
    r"\b(?:can't|cannot|couldn't|could not|don't|do not|didn't)\s+(?:find|see|locate|identify)\s+(?:a|any|the)\s+(?:\w+\s+)?(?:requirement|spec line|r\d+|basis|reason|justification)\b",
    r"\b(?:for|with)\s+no\s+(?:benefit|reason|gain|purpose|value|good reason|apparent reason)\b",
    r"\bnot (?:worth|in scope)\b", r"\bhas no (?:caller|callers|consumer|consumers|user|users|purpose|use)\b",
    r"\bnot part of (?:this|the)\s+(?:change|ticket|pr|pull request|branch|feature|story|task|scope)\b",
    r"\b(?:is|are)\s+(?:\S+\s+){1,6}?(?:needed|necessary)\s*\?",
    r"\bdo(?:es)?\s+(?:we|you|they|it|this|that|the \w+)\s+(?:really\s+|actually\s+)?need\b[^.?;|]{0,60}\?",
    r"\bwhat\s+(?:is|are)\b[^.?;|]{0,40}\bfor\s*\?",
    r"\bwhy\s+(?:is|are|does|do|did)\b[^.?;|]{0,60}\b(?:here|there|exist|need|needs)\b[^.?;|]{0,70}\?",
    r"\bnever\s+(?:used|called|needed|exercised|passed|set|varied|changed)\b",
    r"\bdo(?:es)?n'?t need\b", r"\bdon'?t need\b", r"\b(?:you|we) (?:aren'?t|are not) gonna need\b",
    r"\b(?:wouldn't|would not|shouldn't|should not|won't|will not|don't|do not|can't|cannot)\s+(?:\w+\s+){0,2}?keep\b",
)
STRICT = rx(  # removal, bound to what it acts on
    r"\bremov(?:e|es|ed|ing|al|able)\b", r"\bdelet(?:e|es|ed|ing|ion|able)\b", r"\bdrop(?:s|ped|ping)?\b",
    r"\bstrip(?:s|ped|ping)?(?: out)?\b", r"\brip(?:s|ped|ping)? out\b", r"\btak(?:e|es|ing) out\b",
    r"\bget(?:s|ting)? rid of\b", r"\beliminat(?:e|es|ed|ing)\b", r"\binlin(?:e|es|ed|ing)\b", r"\bscrap(?:s|ped|ping)?\b",
    r"\bdiscard(?:s|ed|ing)?\b", r"\bleav(?:e|ing) (?:it |them |this |these )?out\b", r"\bomit(?:s|ted|ting)?\b",
    r"\bdisposable\b", r"\b(?:kill|nuke|axe|ditch|purge|prune|excise|yank|zap)(?:s|ed|ing)?\b",
)
SOFT = rx(
    r"\bsimplif(?:y|ies|ied|ying)\b", r"\bcollaps(?:e|es|ed|ing)\b", r"\bhard-?cod(?:e|es|ed|ing)\b",
    r"\bcut(?:s|ting)?(?: out)?\b", r"\brevert(?:s|ed|ing)?\b",
    r"\breplac(?:e|es|ed|ing)\s+(?:\w+\s+){0,3}?with\s+(?:a |an |the )?(?:plain|simple|direct|single|constant|literal|fixed)\b",
)
STOP = re.compile(  # where a removal verb stops reaching names
    r"\b(?:and|then)\s+(?:add|use|call|keep|test|replace|document|write|move|make|have|let|pass|set|rename|extract|introduce|include|implement|retain|cover|check|verify)\b|\binstead\b|[;:]",
    re.I)
MODAL = re.compile(  # ... and what a name before a removal verb needs between them
    r"\b(?:can|could|should|may|might|would|must|will|ought to|needs? to|has to|have to|is to|are to|better|best|be|being|been|is|are|was|were|get|gets)\s+(?:(?:\w+ly|simply|just|safely|probably|all|both|also|entirely|completely|easily)\s+)*(?:be\s+)?$",
    re.I)
BARE = re.compile(r"^[\s:=>,.\-]*(?:(?:so|then|just|simply|probably|please|maybe|also)[\s,]+)*$", re.I)
APPROVE_REQ = re.compile(
    r"\b(?:required|requested|specified|mandated|demanded|prescribed|asked for|called for|spelled out|stated|described|defined|needed|necessary|in the spec)\b"
    r"|\b(?:the spec|spec|specification|the requirements?|r(?P<rule>\d+))\b\s+(?:\w+\s+){0,2}?(?:requires?|specifies|mandates?|demands?|asks? for|calls? for|states?|says|defines?|describes?|prescribes?|spells out|wants)\b"
    r"|\bper (?:the spec|r(?P<rule2>\d+))\b|\bas (?:required|specified|requested|described|stated)\b", re.I)
APPROVE_OK = re.compile(
    r"\b(?:is|are|looks?|seems?|appears?|reads?|stays?)\s+(?:\w+\s+){0,2}?(?:correct|right|fine|ok|okay|good|acceptable|appropriate|compliant|conformant|justified|legitimate|legit|reasonable|sound|sensible|expected|intended)\b"
    r"|\b(?:match(?:es|ed)?|follow(?:s|ed)?|implements?|implemented|satisf(?:ies|ied|y)|conforms?|conformed|meets?|fulfils?|fulfills?|honou?rs?|respects?)\b|\bcorrectly\b|\bok\b|\bexactly\b"
    r"|(?<!the )(?<!a )(?<!its )(?<!their )(?<!each )(?<!one )(?<!per-loan )(?<!single )(?<!capped )(?<!that )(?<!this )\bfine\s*(?:[.,;:!)|]|$)", re.I)


def negated_match(clause, match):
    """Whether a negator stands inside the match or within five words before it."""
    inner = clause[match.start():match.end()]
    return rt.negated(clause, match.start()) or rt.negated(inner, len(inner))


def spans(pattern, clause):
    """The (start, end) of every match of `pattern` in `clause` that no negator turns round."""
    return [(m.start(), m.end()) for m in pattern.finditer(clause) if not negated_match(clause, m)]


# A "this" or "that" before one of these is not about a construct: "the spec doesn't cover this case".
CIRCUMSTANCE = (r"cases?|situations?|scenarios?|failures?|errors?(?!\s+handling)|conditions?|paths?|inputs?|edges?|problems?|issues?|"
                r"points?|matters?|questions?|gaps?|bugs?|defects?|findings?|circumstances?|instances?|events?|exceptions?|outcomes?|"
                r"eventualit(?:y|ies)|possibilit(?:y|ies)|combinations?|details?|aspects?|areas?|spots?|moments?|times?")
# What a review calls a construct when it does not name it: "Remove the option and alternate policies."
GENERIC = (r"options?|flags?|switch(?:es)?|settings?|parameters?|arguments?|overrides?|knobs?|modes?|polic(?:y|ies)|strateg(?:y|ies)|variants?|"
           r"choices?|alternatives?|class(?:es)?|modules?|layers?|abstractions?|hierarch(?:y|ies)|registr(?:y|ies)|caches?|loops?|"
           r"wrappers?|decorators?|mechanisms?|machinery|scaffolding|indirection|infrastructure|plumbing|features?|extension points?|"
           r"hooks?|interfaces?|renderers?|frameworks?|additions?|extras?|attempts?|retr(?:y|ies)|delays?|sleeps?|formats?|lookups?")
CIRCUMSTANTIAL = re.compile(r"\b(?:this|that|these|those|such|the|a|an|any|each|every)\s+(?:[\w'-]+\s+)?(?:%s)\b" % CIRCUMSTANCE, re.I)
DESCRIBED = re.compile(r"\b(?:the|this|that|these|those|its|their|all|both|each|any|every|such)\s+(?:[\w'-]+\s+){0,2}?(?:%s)\b" % GENERIC, re.I)
# "Remove the override": the one of the three constructs that the finding named last, if it named one (--rounding replaces R7's rule).
OVERRIDE = re.compile(r"\b(?:the|this|that|these|those|its|their|all|both|each|any|every|such)\s+(?:[\w'-]+\s+){0,2}?overrides?\b", re.I)
# More than the SPEC asks, said of the interface and not of a number: "outside the requested command interface", "beyond the specified
# behavior".
BEYOND = rx(
    r"\b(?:beyond|outside|exceeds?|exceeding|goes beyond|going beyond|over and above)\s+(?:the\s+)?(?:requested|specified|required|"
    r"prescribed|mandated|asked[- ]for)\s+(?:[\w-]+\s+){0,2}?(?:interface|api|cli|commands?|behaviou?rs?|surface|functionality|"
    r"feature set|options?|usage|contract|requirements?)\b")
# "Enforce the specified rule rather than allowing it to be overridden": the fix of an excess construct holds up what the SPEC asks for
# against a choice that someone is offered. A claim about the three excess constructs only ("keep the delay fixed rather than letting
# callers set it" asks the retry for something else and does not call it unrequested), and only in a clause that mentions the SPEC
# ("rejects unknown modes rather than accepting them" is praise).
ALLOWING = rx(
    r"\b(?:rather|instead)\s+(?:than|of)\s+(?:(?:simply|just|actually)\s+)?(?:allow(?:s|ing)?|permit(?:s|ting)?|expos(?:e|es|ing)|"
    r"offer(?:s|ing)?|support(?:s|ing)?|provid(?:e|es|ing)|accept(?:s|ing)?|enabl(?:e|es|ing)|let(?:s|ting)?)\b")
SPEC_REF = re.compile(r"\bR\d+\b|\b(?:spec|specification|requirements?|specified|required|requested|prescribed|mandated|fixed)\b", re.I)
# A saying verb at the end of a cue ("the spec doesn't cover", "nothing in the spec says", "the spec is silent on") whose
# object is a question or a case: the SPEC is silent on a detail, which is a gap to decide and not an unrequested construct.
SAYS = re.compile(r"\b(?:asks?|requires?|calls?|mentions?|specif(?:y|ies)|says?|describes?|states?|covers?|needs?|demands?|"
                  r"mandates?|wants?|defines?|silent|mute|nothing)\W*(?:(?:on|about|regarding|concerning|as to)\W*)?$", re.I)
GAP_TAIL = re.compile(
    r"^\W*(?:(?:on|about|regarding|concerning|as to|for|of|in)\s+)?(?:(?:what|how|whether|when|if|where|which|why|who|exactly|precisely)\b"
    r"|(?:this|that|these|those|such|the|a|an|any|each|every)\s+(?:[\w'-]+\s+)?(?:%s)\b)" % CIRCUMSTANCE, re.I)


# "The cache drops entries after 300 seconds", "The retry omits the sleep after the last attempt": a removal verb in the third
# person describes what code does; a recommendation says "drop it", "should be dropped", "I'd drop", "dropping".
THIRD = re.compile(r"(?:removes|deletes|drops|strips|rips out|takes out|gets rid of|eliminates|inlines|scraps|discards|omits|leaves out|"
                   r"simplifies|collapses|hard-?codes|cuts|reverts|replaces)\b", re.I)
# "without the required message", "does not print the specified header", "the message R11 requires": a negated requirement word
# that says something required is missing, which is not a claim that anything is unrequested. "without implementing any
# requested behavior" and "with no required behavior" are claims, and keep their cue.
DEFINITE = re.compile(r"\b(?:the|its|their|this|that|these|those)\s+$", re.I)


def lacking(text, match):
    """Whether a negated requirement word at `match` says that something required is missing: "the required message" (a
    single word after "the", "its", "this", ...; not the "that" of "modes that R7 does not ask for") or "without the
    message R11 requires"."""
    before = text[:match.start()]
    if re.fullmatch(r"\w+", match.group(0)) and DEFINITE.search(before):
        return True
    cut = max(before.rfind(","), before.rfind(";"), before.rfind(":"), before.rfind("|"))
    tokens = rt.WORD.findall(before[cut + 1:])[-5:]
    without = [i for i, t in enumerate(tokens) if t.lower() == "without"]
    return bool(without) and not any(t.lower().endswith("ing") for t in tokens[without[-1] + 1:])


def is_gap(text, start, end):
    """Whether the cue at text[start:end] says that the SPEC is silent on a detail or a case."""
    return bool(SAYS.search(text[start:end]) and GAP_TAIL.match(text[end:]))


class Clause:
    """What one clause says: the constructs it names, the cues that act on them, and whether it approves."""

    def __init__(self, text):
        self.text = text
        self.names = names(text)
        self.strong = spans(STRONG, text) + [(m.start(), m.end()) for m in SELF.finditer(text)]
        self.strict = spans(STRICT, text)
        self.soft = spans(SOFT, text)
        self.beyond = spans(BEYOND, text)
        self.alternatives = spans(ALLOWING, text) if SPEC_REF.search(text) else []
        approvals, missing = [], []
        for m in APPROVE_REQ.finditer(text):
            if negated_match(text, m):  # "not required" and its kind are cues
                self.strong.append((m.start(), m.end()))
                if lacking(text, m):
                    missing.append((m.start(), m.end()))
            elif not rt.negated_after(text, m.end()):  # "the spec says nothing about it" approves of nothing
                approvals.append(m)
        approvals += [m for m in APPROVE_OK.finditer(text) if not negated_match(text, m)]
        cues = self.strong + self.strict + self.soft + self.beyond + self.alternatives
        self.approvals = [m for m in approvals if not any(s < m.end() and m.start() < e for s, e in cues)]
        # cues that are not claims: the SPEC is silent on a case, or something required is missing
        self.not_claims = [(s, e) for s, e in self.strong if is_gap(text, s, e)] + missing
        # removal verbs that recommend, as against third-person ones that describe
        self.removals = [span for span in self.strict if not THIRD.match(text, span[0])]
        self.softer = [span for span in self.soft if not THIRD.match(text, span[0])]

    def cue(self):
        """Whether the clause carries any cue (what `asks` counts)."""
        return bool(self.strong or self.strict or self.soft or self.beyond or self.alternatives)

    def says_unrequested(self):
        """Whether a strong cue of the clause is a claim that something is unrequested or unneeded: not a statement that the
        SPEC is silent on a detail or a case (nor a part of one: the "in the spec" of "nothing in the spec says what ..."),
        and not one that something required is missing; or it says that something is outside the requested interface."""
        return bool(self.beyond) or any(not any(g0 <= s0 and s1 <= g1 for g0, g1 in self.not_claims) for s0, s1 in self.strong)

    def claims(self):
        """Whether the clause says something is unrequested, unneeded, or removable (what `reports` reads)."""
        return self.says_unrequested() or bool(self.removals or self.softer)

    def described(self):
        """What each recommending removal verb of the clause reaches when it names nothing that it removes but describes it:
        "Remove the override from the command", "Remove the alternative policies" (and keep the specified rounding behavior)."""
        out = []
        for start, end in self.removals:
            stop = STOP.search(self.text, end)
            reach = self.text[end:stop.start() if stop else len(self.text)]
            if DESCRIBED.search(reach) and not self.bound([(start, end)], set(self.names)):
                out.append(reach)
        return out

    def approves(self, rule):
        """Whether the clause approves of a construct that SPEC line `rule` requires (None: no line does): a plain
        approval always counts, one that cites a line counts only for that line."""
        for m in self.approvals:
            number = (m.groupdict().get("rule") or m.groupdict().get("rule2")) if m.re is APPROVE_REQ else None
            if number is None or "R" + number == rule:
                return True
        return False

    def cites(self, rule):
        return bool(re.search(r"\b%s\b" % re.sub(r"^R", "R-?", rule), self.text, re.I))

    def bound(self, verbs, kinds):
        """The constructs (of `kinds`) that the removal `verbs` act on."""
        found = set()
        for start, end in verbs:
            stop = STOP.search(self.text, end)
            limit = stop.start() if stop else len(self.text)
            modal = MODAL.search(self.text[:start])
            for construct, spots in self.names.items():
                if construct not in kinds:
                    continue
                for s, e in spots:
                    if end <= s < limit or (e <= start and ((modal and e <= modal.start()) or BARE.match(self.text[e:start]))):
                        found.add(construct)
        return found

    def retracts(self, rule):
        """Whether a clause that follows a report of a decoy takes it back: it approves, or cites the line, and has no cue."""
        return not self.cue() and (self.approves(rule) or self.cites(rule))


ANAPHOR = re.compile(r"\b(?:it|its|they|them|their|both|all|each|either|neither|none|the (?:whole|entire|rest)|the lot)\b"
                     r"|\b(?:this|that|these|those|such)\b(?!\s+(?:[\w'-]+\s+)?(?:%s)\b)" % CIRCUMSTANCE, re.I)
COLLECTIVE = re.compile(r"\b(?:all|both|each|these|those|they|them|their|three|two|every|none of|neither|the lot|the rest|any of)\b", re.I)
STOPWORDS = set("the a an by in of for any all is are be to spec specification requirement requirements line lines item items as per at here "
                "anywhere really simply just quite very too and or it this that these those so also which with from on its their yet now "
                "already currently least every each only even if then else than".split())
RULE_NUMBER = re.compile(r"r\d+")


def cue_only(clause):
    """A clause that is nothing but a cue, with at most one word of its own: "Not required by any SPEC line",
    "Speculative generality, YAGNI", "Inline it", "Over-built"."""
    text = clause.text
    for start, end in sorted(clause.strong + clause.strict + clause.soft + clause.beyond + clause.alternatives, reverse=True):
        text = text[:start] + " " + text[end:]
    left = [w for w in rt.WORD.findall(text.lower()) if w not in STOPWORDS and not RULE_NUMBER.fullmatch(w)]
    first = rt.WORD.findall(clause.text.lower())[:1]
    if any(re.fullmatch(CIRCUMSTANCE, w) for w in left):  # "This situation is not covered by the spec."
        return False
    return len(left) <= 1 and first not in (["the"], ["a"], ["an"], ["some"])


# "mkdir is outside the retry", "the directory bypasses the retry": the clause is about something else, with the construct as
# its reference point, so a "this" or "it" that follows is not about the construct.
OUTSIDE = re.compile(
    r"\b(?:outside|beyond|bypass(?:es|ed|ing)?|escap(?:es|ed|ing)|avoid(?:s|ed|ing)?|besides|apart from|aside from|other than|"
    r"not (?:covered|handled|caught|protected) by|not (?:subject to|part of|inside|within))\s+(?:(?:the|a|an|its|their|this|that|any)\s+)?"
    r"(?:[\w'-]+\s+){0,2}$", re.I)


def topical(clause):
    """The constructs a clause is about: those it names other than as the reference point of an "outside the retry"."""
    return {construct for construct, spots in clause.names.items()
            if any(not OUTSIDE.search(clause.text[:start]) for start, _ in spots)}


def pointing_back(clause):
    """Whether a clause that names nothing can be about what the clauses before it named: it says it, they, or this (but not
    "this case"), describes the construct ("the option", "the module"), is a few words, or is nothing but the cue."""
    return (bool(ANAPHOR.search(clause.text)) or bool(DESCRIBED.search(clause.text))
            or (rt.words(clause.text) <= 4 and not CIRCUMSTANTIAL.search(clause.text)) or cue_only(clause))


def nearest_excess(recent):
    """The constructs of the three that the finding named last (`recent`: what each of its last clauses that named something
    was about), or none."""
    for found in reversed(recent):
        if any(c in EXCESS for c in found):
            return {c for c in found if c in EXCESS}
    return set()


def reports(raw, trace=None):
    """{"excess": {construct: [clauses]}, "decoys": {construct: [clauses]}}: the clauses that report each construct.
    With a list as `trace`, each report also appends (construct, route, clause, clauses back to the name it points at),
    the route being "named" (a cue in the clause that names it), "removal" (a removal verb that acts on the name),
    "row" (a verdict in a table row), "heading" (a cue in the heading or lead-in above), or "points back"."""
    excess = {name: [] for name in EXCESS}
    decoys = {name: [] for name in DECOYS}
    for block in rt.blocks(raw):
        frames = [Clause(c) for frame in block.frames for c in rt.clauses(frame)]
        frame_cue = any(c.claims() and not c.approves(None) for c in frames)
        named = [c for c in frames if c.names]
        last = topical(named[-1]) if named and not named[-1].approves(None) else set()
        recent, age, hits = [last], 0, []
        parsed = [Clause(t) for t in rt.clauses(block.text, block.kind, names)]
        for i, clause in enumerate(parsed):
            if clause.names:
                routes = {c: "named" for c in clause.names} if clause.says_unrequested() else {}
                for c in clause.bound(clause.removals, set(clause.names)) | clause.bound(clause.softer, {k for k in clause.names if k in EXCESS}):
                    routes.setdefault(c, "removal")
                if clause.alternatives:  # "enforce R7 rather than exposing alternative policies": said of the three only
                    for c in clause.names:
                        if c in EXCESS:
                            routes.setdefault(c, "named")
                if block.kind == "row" and (clause.removals or clause.softer):
                    for c in clause.names:
                        routes.setdefault(c, "row")
                if frame_cue:  # what a heading or lead-in reports, unless the item approves of itself
                    for c in clause.names:
                        if not clause.approves(rule_of(c)):
                            routes.setdefault(c, "heading")
                about = topical(clause)  # a name that is only the reference point of "outside the retry" is not reported
                here = [(i, c, route, 0) for c, route in routes.items() if c in about and not (c in DECOYS and clause.approves(rule_of(c)))]
                hits += here
                described = clause.described()
                if described and age < 3:  # "Remove the alternative policies and keep the specified rounding behavior": the name is what is kept
                    pool = (nearest_excess(recent) if any(OVERRIDE.search(r) for r in described) else set()) or last
                    hits += [(i, c, "points back", age + 1) for c in pool - {h[1] for h in here}
                             if c in EXCESS or (c not in clause.names and not clause.approves(rule_of(c)))]
                last = {c for c in topical(clause) if not (c in DECOYS and clause.approves(rule_of(c)))}
                recent, age = (recent + [last])[-4:], 0
            else:
                age += 1
                if clause.claims() and age <= 3 and pointing_back(clause):
                    if COLLECTIVE.search(clause.text):
                        pool = set().union(*recent)
                    else:
                        pool = (nearest_excess(recent) if OVERRIDE.search(clause.text) else set()) or last
                    hits += [(i, c, "points back", age) for c in pool if c in EXCESS or not clause.approves(rule_of(c))]
        for i, construct, route, back in hits:
            if construct in DECOYS and any(p.retracts(rule_of(construct)) for p in parsed[i + 1:i + 3]):
                continue
            (excess if construct in EXCESS else decoys)[construct].append(parsed[i].text)
            if trace is not None:
                trace.append((construct, route, parsed[i].text, back))
    return {"excess": excess, "decoys": decoys}


# ---- the findings of a review ------------------------------------------------------------------------------------

NONFINDING = re.compile(  # a section that is not a finding: a summary, or a record of what was checked and found right
    r"\b(?:summary|overview|verdict|conclusion|overall|bottom line|tl;?dr|scope of (?:the )?review|how i reviewed|method|approach|"
    r"context|background|verified|checked|looks? good|looked good|no issues|nothing to flag|passes|passing|what is (?:right|fine|correct)|"
    r"what (?:i|we) (?:checked|verified|confirmed)|positives?|strengths|ok as written|fine as|found right|"
    r"left alone|leave alone|all good|conforms|conforming)\b", re.I)


def units(blocks):
    """The findings of a review: [(title, [Block])]. A heading section holds one finding, unless it lists items or rows,
    which are then the findings; a heading that only introduces deeper headings holds none."""
    sections = {}
    for b in blocks:
        sections.setdefault(b.section, []).append(b)
    headings = [b for b in blocks if b.kind == "heading"]
    out = []
    for number, group in sections.items():
        heading = next((b for b in group if b.kind == "heading"), None)
        body = [b for b in group if b.kind != "heading"]
        title = heading.text if heading else ""
        listed = [b for b in body if b.kind in ("item", "row")]
        if number == 0:
            out += [("", [b]) for b in body]
        elif listed:
            out += [(title, [b]) for b in listed] + [(title, [b]) for b in body if b.kind == "para"]
        elif body:
            out.append((title, group))
        else:  # a heading with nothing under it is a finding of its own only when no deeper heading follows
            later = [h for h in headings if h.section == number + 1]
            if not (later and later[0].level > heading.level):
                out.append((title, group))
    return out


def finding_sequence(unit):
    title, group = unit
    frames = [Clause(c) for frame in group[0].frames for c in rt.clauses(frame)]
    return frames + [Clause(c) for b in group for c in rt.clauses(b.text, b.kind)]


def split_units(units_):
    """The units of a review, with a paragraph written one finding to a line split into its findings."""
    out = []
    for title, group in units_:
        if len(group) == 1 and group[0].kind == "para" and len(group[0].lines) > 1:
            for text in rt.findings_in(group[0]):
                piece = rt.Block("para", text, group[0].frames, group[0].section)
                out.append((title, [piece]))
        else:
            out.append((title, group))
    return out


# ---- what a finding asks for -----------------------------------------------------------------------------------

ADD_WORDS = (r"add|adds|include|introduce|implement|write|extend|cover|document|validate|handle|guard|log|support|expose|"
             r"enforce|assert|ensure|provide|create|wrap|sanitize|escape|parametri[sz]e|catch|reject|test|check|verify|"
             r"raise|report|surface|expand|improve|clarify")
ADD_VERBS = (r"add|adds|include|introduce|implement|write|extend|cover|document|validate|guard|enforce|assert|ensure|provide|wrap|"
             r"sanitize|escape|parametri[sz]e|catch|reject|expose|surface")
ADD_ASK = rx(
    r"^(?:[A-Za-z ]{1,24}:\s*)?(?:(?:please|also|and|then|so|consider|suggest|recommend|worth|maybe|probably)\s+)*(?:%s)\b" % ADD_WORDS,
    r"(?:[,;:]\s+|\b(?:and|then|also|please|so|consider|suggest|recommend|worth|maybe|probably)\s+)(?:%s)\b" % ADD_VERBS,
    r"\b(?:should|needs? to|must|ought to|could|would|might|i'd|i would|we should|worth|ought)\s+(?:also\s+|probably\s+|really\s+)?(?:help to\s+|be (?:good|better|nice|useful|helpful) to\s+)?(?:%s|make|have|get|be (?:tested|covered|validated|documented|checked|logged|handled|configurable))\b" % ADD_WORDS,
    r"\b(?:missing|lacks?|lacking|absent|untested|undocumented|unvalidated|unhandled|unchecked|uncovered)\b",
    r"\bnothing\s+(?:covers|tests|exercises|checks|asserts|verifies|pins)\b",
    r"\b(?:could|would|should|needs?)\s+(?:use|do with|benefit from|have)\s+(?:a|an|some|more|one|its)\b",
    r"\bno\s+(?:\w+\s+){0,2}?(?:tests?|test coverage|coverage|validation|error handling|handling|docs?|documentation|logging|checks?|guard|assertions?)\b",
    r"\b(?:not|never|isn'?t|aren'?t|wasn'?t|weren'?t)\s+(?:\w+\s+)?(?:tested|covered|validated|handled|documented|checked|logged|exercised|asserted)\b",
    r"\bwithout\s+(?:a\s+|any\s+)?(?:tests?|validation|checks?|guards?|documentation|docs|coverage|error handling)\b",
    r"\b(?:does(?:n't|\s+not)|do(?:es)?n't|don't)\s+(?:\w+\s+){0,2}?(?:validate|handle|check|verify|cover|test|document|log|guard|sanitize|escape|report|surface|catch)\b",
)


DEFECT_WORDS = rx(r"\breverse\b", r"\btotal_owed\b", r"\bcents_per_day\b", r"\bdays\s*[*x\u00d7]", r"\bsort key\b", r"\brow\.fine\b")


def asks(raw):
    """(findings that ask to add, findings that ask to remove). A finding asks to add when a clause of it, or of the
    headings above it, says to add, test, validate, document, ... or that something is missing or untested; it asks
    to remove when a clause carries a cue of the kinds above, unless the clause is the fix of a defect ("drop
    `reverse=True`"). Summaries and sections that only record what was found right are not findings."""
    add = remove = 0
    for unit in split_units(units(rt.blocks(raw))):
        if NONFINDING.search(unit[0]):
            continue
        sequence = finding_sequence(unit)
        add += any(ADD_ASK.search(c.text) for c in sequence)
        remove += any(c.cue() and not DEFECT_WORDS.search(c.text) for c in sequence)
    return add, remove


MOST = 400_000  # characters of a review that are read; a longer one is cut here


def analyze(raw):
    """Everything a check needs to know about one review."""
    raw = raw[:MOST]
    found = reports(raw)
    add, remove = asks(raw)
    return {"excess": found["excess"], "decoys": found["decoys"], "asks_add": add, "asks_remove": remove, "words": rt.words(raw)}
