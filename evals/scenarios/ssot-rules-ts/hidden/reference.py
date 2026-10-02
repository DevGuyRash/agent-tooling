"""Reference for ssot-rules-ts: the shop's quote (as the fixture computes it) and the product feed (as
docs/feed.md specifies it), both under a shipping rule passed in, so the check can compute what each
command should print after it edits one value of the rule.

RULE is the fixture's rule (src/checkout.ts). A rule is a dict: packaging (grams added to every parcel),
free_from (goods in cents from which German orders ship free), eu (zone EU country codes), and rates
(rows of (up to grams, DE, EU, WORLD) in cents). Two optional flags change how the rule compares, as an
edit of the rule's wording would: free_strict (German orders ship free only over free_from, not at it) and
band_exclusive (a parcel at a band's limit goes in the next band)."""
import copy

RULE = {
    "packaging": 180,
    "free_from": 4900,
    "eu": ["AT", "BE", "BG", "CY", "CZ", "DK", "EE", "ES", "FI", "FR", "GR", "HR", "HU",
           "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK"],
    "rates": [(500, 449, 990, 1590), (1000, 549, 1290, 2190), (2000, 649, 1690, 2990),
              (5000, 899, 2390, 4490), (10000, 1199, 3490, 6990)],
}
ZONES = {"DE": 1, "EU": 2, "WORLD": 3}


class Refused(Exception):
    """What quote refuses (exit status 1)."""


def mutated(**changes):
    """RULE with some parts replaced; rates as {(row, zone): cents}, eu_swap as (code out, code in)."""
    rule = copy.deepcopy(RULE)
    for key, value in changes.items():
        if key == "rates":
            rows = [list(r) for r in rule["rates"]]
            for (row, zone), cents in value.items():
                rows[row][ZONES[zone]] = cents
            rule["rates"] = [tuple(r) for r in rows]
        elif key == "eu_swap":
            old, new = value
            rule["eu"] = [new if c == old else c for c in rule["eu"]]
        else:
            rule[key] = value
    return rule


def zone(rule, country):
    return "DE" if country == "DE" else "EU" if country in rule["eu"] else "WORLD"


def shipping(rule, country, goods, item_grams):
    """(parcel grams, shipping cents) for one parcel."""
    grams = rule["packaging"] + item_grams
    band = next((r for r in rule["rates"] if (grams < r[0] if rule.get("band_exclusive") else grams <= r[0])), None)
    if band is None:
        raise Refused(f"parcel of {grams} g is over the 10 kg limit")
    z = zone(rule, country)
    free = goods > rule["free_from"] if rule.get("free_strict") else goods >= rule["free_from"]
    return grams, (0 if z == "DE" and free else band[ZONES[z]])


def quote(rule, catalog, order):
    """quote --json as a dict, or raise Refused."""
    products = {p["sku"]: p for p in catalog["products"]}
    lines, goods, item_grams = [], 0, 0
    if not order["lines"]:
        raise Refused("no lines")
    for line in order["lines"]:
        p = products.get(line["sku"])
        if p is None or not p.get("active", True):
            raise Refused(f"unknown or inactive product {line['sku']}")
        amount = p["price"] * line["qty"]
        lines.append({"sku": p["sku"], "title": p["title"], "qty": line["qty"], "price": p["price"], "amount": amount})
        goods += amount
        item_grams += p["grams"] * line["qty"]
    grams, ship = shipping(rule, order["country"], goods, item_grams)
    return {"order": order["id"], "country": order["country"], "lines": lines, "goods": goods, "grams": grams,
            "shipping": ship, "total": goods + ship}


def cents(n):
    return f"{n // 100}.{n % 100:02d}"


def feed(rule, catalog, countries):
    """The feed's standard output for `feed CATALOG --countries ...`."""
    out = ["sku\ttitle\tprice\tcountry\tshipping"]
    for p in catalog["products"]:
        if not p.get("active", True):
            continue
        for c in countries:
            _, ship = shipping(rule, c, p["price"], p["grams"])
            out.append(f"{p['sku']}\t{p['title']}\t{cents(p['price'])}\t{c}\t{cents(ship)}")
    return "\n".join(out) + "\n"
