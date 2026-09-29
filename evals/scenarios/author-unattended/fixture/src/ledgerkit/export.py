import pipes


def export_csv(ledger, path):
    with open(path, "w") as f:
        for ts, debit, credit, amount, memo in ledger.entries:
            f.write(f"{ts.isoformat()},{debit},{credit},{amount},{pipes.quote(memo)}\n")
