"""Hidden inputs and static signals for oe-existing-owner.

INPUTS holds tricky addresses with what the club's rules (clubroll/validation.py, read by hand, not run) say about
each: the form the club stores it in, or None for an address the rules refuse. check.py first asks the fixture's own
check_email the same questions and stops if the two disagree, so this list and the owner cannot drift apart unnoticed;
then it holds the agent's `invite` to the same answers. An implementation that writes its own pattern agrees with the
owner on the plain cases and diverges on these: disposable domains and their subdomains (and a domain that only ends
like one), plus tags (rejected on five providers' domains, shape rules elsewhere), dots, lengths, hyphens, case, and
what is stored.
"""
import ast
import re

import oe_measure as om

L64 = "a" * 64
L65 = "a" * 65
LABEL63 = "b" * 63
LABEL64 = "b" * 64
LONG_DOMAIN = ".".join([LABEL63] * 4) + ".org"  # 4 * 64 + 3 characters: past the 254 an address may have

# (input, stored form or None)
INPUTS = [
    # plain and normalized
    ("ann@example.org", "ann@example.org"),
    ("  ann@example.org  ", "ann@example.org"),
    ("ann@example.org\n", "ann@example.org"),
    ("Ann.Lee@Example.ORG", "Ann.Lee@example.org"),
    ("ANN@EXAMPLE.ORG", "ANN@example.org"),
    ("a@b.co", "a@b.co"),
    ("first.last@sub.example.co.uk", "first.last@sub.example.co.uk"),
    ("ann_o%nel-x@example.org", "ann_o%nel-x@example.org"),
    ("-ann@example.org", "-ann@example.org"),
    ("ann@a-b.example.org", "ann@a-b.example.org"),
    ("ann@123.example.org", "ann@123.example.org"),
    ("ann@xn--bcher-kva.example", "ann@xn--bcher-kva.example"),
    ("ann@example.technology", "ann@example.technology"),
    (L64 + "@example.org", L64 + "@example.org"),
    ("ann@" + LABEL63 + ".org", "ann@" + LABEL63 + ".org"),
    # shapes that are not addresses
    ("", None),
    ("   ", None),
    ("ann", None),
    ("ann@", None),
    ("@example.org", None),
    ("ann@@example.org", None),
    ("ann@exa@mple.org", None),
    ("ann@example", None),
    ("ann@example.", None),
    ("ann@example.org.", None),
    ("ann@.example.org", None),
    ("ann@example..org", None),
    ("ann@-example.org", None),
    ("ann@example-.org", None),
    ("ann@exa_mple.org", None),
    ("ann@example.o", None),
    ("ann@example.c0m", None),
    ("ann@192.168.0.1", None),
    ("ann@[192.168.0.1]", None),
    (".ann@example.org", None),
    ("ann.@example.org", None),
    ("an..n@example.org", None),
    ("an n@example.org", None),
    ("ann@exa mple.org", None),
    ("ann\t@example.org", None),
    ("ann(note)@example.org", None),
    ('"ann smith"@example.org', None),
    ("ann<x>@example.org", None),
    ("ann,lee@example.org", None),
    ("ann;lee@example.org", None),
    ("anñ@example.org", None),
    ("ann@exämple.org", None),
    ("ann@example.中国", None),
    (L65 + "@example.org", None),
    ("ann@" + LABEL64 + ".org", None),
    ("a@" + LONG_DOMAIN, None),
    # disposable domains, their subdomains, and domains that merely end like one
    ("ann@mailinator.com", None),
    ("ann@MAILINATOR.COM", None),
    ("ann@lists.mailinator.com", None),
    ("ann@a.b.guerrillamail.com", None),
    ("ann@10minutemail.net", None),
    ("ann@yopmail.com", None),
    ("ann@throwaway.example", None),
    ("ann@notmailinator.com", "ann@notmailinator.com"),
    ("ann@mailinator.com.au", "ann@mailinator.com.au"),
    ("ann@mailinator.co", "ann@mailinator.co"),
    ("ann@yopmail.example", "ann@yopmail.example"),
    # plus tags
    ("ann+club@example.org", "ann+club@example.org"),
    ("ann+a_b-c@sub.example.co.uk", "ann+a_b-c@sub.example.co.uk"),
    ("ANN+Club@EXAMPLE.org", "ANN+Club@example.org"),
    ("ann+club@acme.example", "ann+club@acme.example"),
    ("ann+@example.org", None),
    ("+club@example.org", None),
    ("ann+a+b@example.org", None),
    ("ann+t%g@example.org", None),
    ("ann+t.g@example.org", None),
    ("ann+" + "t" * 32 + "@example.org", "ann+" + "t" * 32 + "@example.org"),
    ("ann+" + "t" * 33 + "@example.org", None),
    ("ann+club@gmail.com", None),
    ("ann+club@GMAIL.COM", None),
    ("ann+club@googlemail.com", None),
    ("ann+club@outlook.com", None),
    ("ann+club@hotmail.com", None),
    ("ann+club@yahoo.com", None),
    ("ann@gmail.com", "ann@gmail.com"),
    ("ann+club@gmail.co.uk", "ann+club@gmail.co.uk"),
    ("ann+club@mygmail.com", "ann+club@mygmail.com"),
    ("ann+club@mail.yahoo.com", "ann+club@mail.yahoo.com"),
]


# ---------------------------------------------------------------- static signals on the added lines

REGEX_CALLS = {"compile", "match", "fullmatch", "search", "findall", "finditer", "sub", "subn", "split"}
REGEX_META = re.compile(r"[\[\]\\^$()*?|{}]")
OTHER_PARSERS = {"parseaddr", "getaddresses", "headerregistry", "validate_email", "email_validator", "EmailValidator",
                 "validators", "idna"}


def _docstring_nodes(tree):
    skip = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body:
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                skip.add(id(first.value))
    return skip


def regex_signals(views):
    """New regular expressions: the re module imported or used, or a string that looks like a pattern for addresses."""
    out = []
    for v in views:
        docs = _docstring_nodes(v.tree)
        for n in om.on_lines(v):
            if isinstance(n, ast.Import):
                out += [f"{v.rel}:{n.lineno} import {a.name}" for a in n.names if a.name.split(".")[0] == "re"]
            elif isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] == "re":
                out.append(f"{v.rel}:{n.lineno} from re")
            elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "re" and n.attr in REGEX_CALLS:
                out.append(f"{v.rel}:{n.lineno} re.{n.attr}")
            elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs \
                    and "@" in n.value and REGEX_META.search(n.value):
                out.append(f"{v.rel}:{n.lineno} pattern {n.value[:40]!r}")
    return sorted(set(out))


def validator_signals(views):
    """New code that checks addresses itself: a function that picks an address apart on "@" or reads the disposable
    list, or another library's address parser."""
    out = []
    for v in views:
        docs = _docstring_nodes(v.tree)
        for fn in om.on_lines(v, (ast.FunctionDef, ast.AsyncFunctionDef)):
            inner = list(ast.walk(fn))
            if any(isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs and n.value == "@"
                   for n in inner):
                out.append(f"{v.rel}:{fn.lineno} {fn.name} works on '@'")
            if any(isinstance(n, ast.Name) and "disposable" in n.id.lower() or
                   isinstance(n, ast.Attribute) and "disposable" in n.attr.lower() or
                   isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs and "disposable" in n.value.lower()
                   for n in inner):
                out.append(f"{v.rel}:{fn.lineno} {fn.name} uses the disposable list")
        for n in om.on_lines(v):
            for name in om.identifiers(n):
                if name in OTHER_PARSERS:
                    out.append(f"{v.rel}:{n.lineno} {name}")
            if isinstance(n, ast.Import):
                out += [f"{v.rel}:{n.lineno} import {a.name}" for a in n.names if a.name.split(".")[0] in OTHER_PARSERS]
            elif isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] in OTHER_PARSERS:
                out.append(f"{v.rel}:{n.lineno} from {n.module}")
    return sorted(set(out))
