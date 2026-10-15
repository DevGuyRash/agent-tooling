"""The club's input rules. Whatever people type in is checked here."""
import re
from functools import lru_cache
from pathlib import Path

DISPOSABLE_FILE = Path(__file__).with_name("data") / "disposable_domains.txt"

# Plus-addressing (name+tag@host) lets one person make many accounts out of one mailbox, so these providers' domains
# do not take it. Everywhere else a plus tag is fine.
NO_PLUS_TAGS = frozenset({"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "yahoo.com"})

_LOCAL = re.compile(r"[A-Za-z0-9._%+-]{1,64}")
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_TLD = re.compile(r"[a-z]{2,24}")
_TAG = re.compile(r"[A-Za-z0-9_-]{1,32}")


class InvalidEmail(ValueError):
    pass


class InvalidName(ValueError):
    pass


@lru_cache(maxsize=1)
def disposable_domains():
    lines = DISPOSABLE_FILE.read_text(encoding="utf-8").splitlines()
    return frozenset(line.strip().lower() for line in lines if line.strip() and not line.startswith("#"))


def check_email(address):
    """The address in the form the club stores it (no surrounding space, domain in lower case), or InvalidEmail."""
    address = address.strip()
    if len(address) > 254 or address.count("@") != 1:
        raise InvalidEmail(f"not an email address: {address!r}")
    local, domain = address.split("@")
    domain = domain.lower()
    if not _LOCAL.fullmatch(local) or local.startswith(".") or local.endswith(".") or ".." in local:
        raise InvalidEmail(f"bad local part: {local!r}")
    labels = domain.split(".")
    if len(labels) < 2 or not all(_LABEL.fullmatch(label) for label in labels) or not _TLD.fullmatch(labels[-1]):
        raise InvalidEmail(f"bad domain: {domain!r}")
    if any(".".join(labels[i:]) in disposable_domains() for i in range(len(labels))):
        raise InvalidEmail(f"disposable domain: {domain!r}")
    if "+" in local:
        base, _, tag = local.partition("+")
        if domain in NO_PLUS_TAGS:
            raise InvalidEmail(f"{domain} does not take plus tags")
        if not base or not _TAG.fullmatch(tag):
            raise InvalidEmail(f"bad plus tag in {local!r}")
    return f"{local}@{domain}"


def check_name(name):
    """The name with its spaces tidied, or InvalidName."""
    name = " ".join(name.split())
    if not 1 <= len(name) <= 80:
        raise InvalidName("a name is 1 to 80 characters")
    return name
