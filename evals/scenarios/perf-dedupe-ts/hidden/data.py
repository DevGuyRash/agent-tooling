"""Deterministic ledgers and rolling exports for the hidden checks:

    python3 data.py PER_DAY LEDGER_DAYS SEED OUT_DIR    writes OUT_DIR/ledger.csv and OUT_DIR/export.csv

The ledger holds LEDGER_DAYS days of transactions for 30 stores, about PER_DAY a day, up to yesterday (D-1)
as last night's import left it. Tonight's export is rolling: days D-2, D-1, and D. About 1.5% of the
transactions of D-2 and D-1 settled late, so they are in tonight's export but not yet in the ledger. About 1
transaction in 250 has an identical twin (the same card, till, minute, and amount: someone paying twice),
in the ledger and the export alike, and about 1 in 300 is a refund. Some tills send lower-case store codes.
Export lines are ordered by date, time, store, and terminal, as the processor writes them.
"""
import random
import sys
from datetime import date, timedelta
from itertools import accumulate
from pathlib import Path

ITEMS = [275, 300, 325, 350, 395, 425, 450, 480, 520, 545, 595, 650, 725, 895]
STORES = [f"S{n:02d}" for n in range(1, 31)]
STORE_WEIGHTS = list(accumulate(1 + (n % 7) for n in range(30)))
HOURS = list(range(6, 22))
HOUR_WEIGHTS = list(accumulate([3, 9, 10, 8, 6, 5, 7, 6, 4, 4, 5, 4, 3, 2, 2, 1]))
LOWER_CASE_TILL = 4      # till 4 in the stores below sends its store code in lower case
OLD_TILL_STORES = {"S03", "S11", "S19", "S27"}
TONIGHT = date(2026, 9, 30)


def _day(rng, day, per_day, cards):
    """One day's transactions as (date, time, store, terminal, last4, cents) tuples, in time order."""
    n = per_day + rng.randint(-per_day // 10, per_day // 10)
    stores = rng.choices(STORES, cum_weights=STORE_WEIGHTS, k=n)
    hours = rng.choices(HOURS, cum_weights=HOUR_WEIGHTS, k=n)
    out = []
    for store, hour in zip(stores, hours):
        time = f"{hour:02d}:{rng.randrange(60):02d}"
        terminal = rng.randint(1, 4)
        card = rng.choice(cards) if rng.random() < 0.6 else f"{rng.randrange(10000):04d}"
        if rng.random() < 1 / 300:
            cents = -rng.choice(ITEMS)
        else:
            cents = sum(rng.choice(ITEMS) for _ in range(rng.randint(1, 3)))
        t = (day.isoformat(), time, store, terminal, card, cents)
        out.append(t)
        if rng.random() < 1 / 250:
            out.append(t)
    out.sort(key=lambda t: (t[1], t[2], t[3]))
    return out


def generate(per_day, ledger_days, seed):
    """(ledger lines, export lines): the ledger's data lines and the export's, without headers."""
    rng = random.Random(seed)
    cards = [f"{rng.randrange(10000):04d}" for _ in range(max(1000, per_day))]
    first = TONIGHT - timedelta(days=ledger_days)
    days = {first + timedelta(days=i): None for i in range(ledger_days + 1)}  # through D
    for day in days:
        days[day] = _day(rng, day, per_day, cards)
    rolling = [TONIGHT - timedelta(days=2), TONIGHT - timedelta(days=1), TONIGHT]
    ledger = []
    for day, txs in days.items():
        if day == TONIGHT:
            continue
        for t in txs:
            if day in rolling and rng.random() < 0.015:
                continue  # settled late: not in the ledger yet
            ledger.append(f"{t[0]}T{t[1]},{t[2]},{t[3]},{t[4]},{t[5]}")
    export = []
    for day in rolling:
        for t in days[day]:
            store = t[2].lower() if t[3] == LOWER_CASE_TILL and t[2] in OLD_TILL_STORES else t[2]
            cents = abs(t[5])
            export.append(f"{t[0]},{t[1]},{store},{t[3]},************{t[4]},{cents // 100}.{cents % 100:02d},"
                          f"{'REFUND' if t[5] < 0 else 'SALE'}")
    return ledger, export


def write(per_day, ledger_days, seed, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger, export = generate(per_day, ledger_days, seed)
    (out_dir / "ledger.csv").write_text("ts,store,terminal,card,amount_cents\n" + "".join(l + "\n" for l in ledger))
    (out_dir / "export.csv").write_text("Date,Time,Store,Terminal,Card,Amount,Type\n" + "".join(l + "\n" for l in export))


if __name__ == "__main__":
    write(int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4])
