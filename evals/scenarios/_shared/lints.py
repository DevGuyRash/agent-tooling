"""Deterministic signals about instruction text an agent produced."""
import re

HISTORY = re.compile(r"(?i)\b(update[sd]?:|note:|clarif(y|ied|ication)|previously|used to|originally|was (read|interpreted|misread)|misread|misinterpret|changed from|no longer|now (only|just)|changelog|revised to)\b")
GENERIC_DUTY = re.compile(r"(?i)(report (what|the (result|outcome|status))|summar(y|ize) (of )?(what|your|the changes)|before (claiming|declaring|reporting) (it |the (task|work) )?(is )?(done|complete)|verify (your|all) (work|changes)|when (you are |you're )?(done|finished|complete)|final (report|summary)|handoff)")
DEGREE = re.compile(r"(?i)\b(appropriate(ly)?|as needed|where relevant|materially|consequential|sufficient(ly)?|reasonabl[ey]|proportionate(ly)?|when warranted|as applicable)\b")
META = re.compile(r"(?i)\b(this (skill|document|section|file) (is|was|describes|explains|provides|aims)|the following (section|list)|as described (above|below)|in this (skill|document))\b")


def words(text):
    return len(text.split())


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def signals(text):
    body = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)
    return {
        "words": words(body),
        "history_hits": len(HISTORY.findall(body)),
        "generic_duty_hits": len(GENERIC_DUTY.findall(body)),
        "degree_hits": len(DEGREE.findall(body)),
        "meta_hits": len(META.findall(body)),
        "shall_not": len(re.findall(r"\bSHALL NOT\b|\bMUST NOT\b|^\s*[-*]?\s*(?:Never|Do not|Don't)\b", body, re.M)),
    }
