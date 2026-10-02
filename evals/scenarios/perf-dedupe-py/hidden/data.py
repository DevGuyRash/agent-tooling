"""Deterministic storefront exports for the hidden checks: python3 data.py ROWS SEED OUT.csv

People get one to eight accounts created at different times over three years, so a person's rows are spread
through the export. Accounts carry the person's email or phone in the forms customers type (case, spaces,
punctuation, a country code), blanks, junk values, placeholders, and now and then a new address or number;
a few people share a phone (households), so some people are tied together only through a chain of rows.
About 1 in 200 accounts was migrated from the old shop: a high customer_id with an older created_at. Some
accounts are created in the same second. Rows are ordered by customer_id, as the storefront writes them.
"""
import csv
import random
import sys
from datetime import datetime, timedelta, timezone
from itertools import accumulate

FIRST = ["Ava", "Ben", "Chloe", "Dev", "Elena", "Femi", "Grace", "Hiro", "Ines", "Jonah", "Kai", "Lena", "Mateo",
         "Nadia", "Omar", "Priya", "Quinn", "Rosa", "Sven", "Tara", "Uma", "Viktor", "Wen", "Ximena", "Yusuf", "Zoe",
         "Ana Lucia", "Jean-Luc", "Mary", "Sam", ""]
LAST = ["Abara", "Brennan", "Castillo", "Dubois", "Eriksen", "Fischer", "Gallagher", "Haddad", "Ivanova", "Jensen",
        "Kowalski", "Lindqvist", "Moreau", "Nakamura", "O'Brien", "Petrov", "Quigley", "Rossi", "Silva", "Tanaka",
        "Underwood", "Varga", "Whitfield", "Xu", "Yilmaz", "Zimmer", "Marsh, Jr.", 'Smith "Smitty"', ""]
DOMAINS = ["example.com", "example.net", "example.org", "mail.example", "post.example", "inbox.example"]
JUNK_EMAILS = ["none", "n/a", "NA", "no email", "-", "x"]
PLACEHOLDERS = ["000-000-0000", "111-111-1111", "(999) 999-9999", "1-555-555-5555", "0", "n/a", "555-0100"]
ACCOUNT_COUNTS, ACCOUNT_WEIGHTS = [1, 2, 3, 4, 5, 6, 8], list(accumulate([55, 24, 10, 5, 3, 2, 1]))
ORDER_COUNTS, ORDER_WEIGHTS = list(range(13)), list(accumulate([4, 30, 18, 12, 9, 7, 5, 4, 3, 3, 2, 2, 1]))
START = datetime(2022, 1, 1, tzinfo=timezone.utc)
SPAN = 3 * 365 * 24 * 3600


def _email_variant(rng, email):
    r = rng.random()
    if r < 0.5:
        return email
    if r < 0.7:
        return email.upper() if rng.random() < 0.3 else email.capitalize()
    if r < 0.85:
        return f" {email} " if rng.random() < 0.5 else email + " "
    local, domain = email.split("@")
    return f"{local.title()}@{domain.upper()}"


def _phone_variant(rng, digits):
    a, b, c = digits[:3], digits[3:6], digits[6:]
    return rng.choice([digits, f"({a}) {b}-{c}", f"{a}-{b}-{c}", f"{a}.{b}.{c}", f"+1 {a} {b} {c}", f"1-{a}-{b}-{c}",
                       f"+1 ({a}) {b}-{c}", f"{a} {b} {c}"])


def _new_phone(rng):
    while True:
        digits = f"{rng.randint(201, 989)}555{rng.randint(0, 9999):04d}"
        if len(set(digits)) > 1:
            return digits


def generate(rows, seed):
    """A list of export rows (lists of strings), ordered by customer_id."""
    rng = random.Random(seed)
    accounts = []  # (created second, row fields without id)
    serial = 0
    households = []
    while len(accounts) < rows:
        serial += 1
        first, last = rng.choice(FIRST), rng.choice(LAST)
        email = f"{(first or 'guest').lower().replace(' ', '.')}.{(last or 'x').lower()[:6]}{serial}@{rng.choice(DOMAINS)}"
        email = email.replace("'", "").replace(",", "").replace('"', "")
        if households and rng.random() < 0.03:
            phone = rng.choice(households)  # someone else in the household uses the same number
        else:
            phone = _new_phone(rng)
            if rng.random() < 0.05:
                households.append(phone)
        k = rng.choices(ACCOUNT_COUNTS, cum_weights=ACCOUNT_WEIGHTS)[0]
        born = rng.randrange(SPAN)
        for n in range(k):
            created = min(SPAN - 1, born + (0 if n == 0 else rng.randrange(SPAN // 3)))
            r = rng.random()
            if r < 0.68:
                e = _email_variant(rng, email)
            elif r < 0.80:
                e = ""
            elif r < 0.86:
                e = rng.choice(JUNK_EMAILS)
            else:
                e = f"{(first or 'g').lower()[:3]}{rng.randint(10, 99999)}@{rng.choice(DOMAINS)}"  # a new address
            r = rng.random()
            if r < 0.50:
                p = _phone_variant(rng, phone)
            elif r < 0.78:
                p = ""
            elif r < 0.86:
                p = rng.choice(PLACEHOLDERS)
            else:
                p = _phone_variant(rng, _new_phone(rng))  # a new number
            orders = rng.choices(ORDER_COUNTS, cum_weights=ORDER_WEIGHTS)[0]
            spent = orders * 800 + int(rng.random() * orders * 8200)
            accounts.append([created, first if rng.random() > 0.05 else first[:1], last, e, p, str(orders),
                             f"{spent // 100}.{spent % 100:02d}", "yes" if rng.random() < 0.4 else "no"])
    accounts = accounts[:rows]
    accounts.sort(key=lambda a: a[0])
    for i in range(1, len(accounts)):
        if rng.random() < 0.01:
            accounts[i][0] = accounts[i - 1][0]  # created in the same second as the account before it
    migrated = [rng.random() < 0.005 for _ in accounts]
    numbers = [0] * len(accounts)
    next_id = 100000
    for i in range(len(accounts)):
        if not migrated[i]:
            numbers[i] = next_id
            next_id += rng.randint(1, 3)
    for i in range(len(accounts)):  # migrated accounts got new numbers after everyone else, keeping created_at
        if migrated[i]:
            numbers[i] = next_id
            next_id += 1
    out = []
    for number, a in zip(numbers, accounts):
        created = (START + timedelta(seconds=a[0])).strftime("%Y-%m-%dT%H:%M:%SZ")
        out.append([str(number), created, *a[1:]])
    out.sort(key=lambda r: int(r[0]))
    return out


HEADER = ["customer_id", "created_at", "first_name", "last_name", "email", "phone", "orders", "total_spent",
          "accepts_marketing"]


def write(rows, seed, path):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(HEADER)
        writer.writerows(generate(rows, seed))


if __name__ == "__main__":
    write(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3])
