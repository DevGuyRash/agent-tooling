"""Column layouts of each bank's CSV export."""

BANKS = {
    "chase": {"date": "Posting Date", "date_format": "%m/%d/%Y", "description": "Description",
              "amount": "Amount", "type": "Type"},
    "ally": {"date": "Date", "date_format": "%Y-%m-%d", "description": "Description",
             "debit": "Debit", "credit": "Credit"},
    "schwab": {"date": "Date", "date_format": "%m/%d/%Y", "description": "Description",
               "amount": "Amount", "type": "Type"},
}


def required_columns(bank):
    layout = BANKS[bank]
    return [layout[k] for k in ("date", "description", "amount", "debit", "credit", "type") if k in layout]
