# Household budget

Shared budget for the apartment. `budget-2026-09.csv` tracks this month's spending by category.

Categories are fixed — see `categories.txt` (Housing, Utilities, Groceries, Transport, Subscriptions, Entertainment, Savings, Misc). If something doesn't fit neatly, use the closest one rather than inventing a new one.

Before sending an updated copy to anyone, run:

    python3 validate.py budget-2026-09.csv

It checks that every category is one of the approved ones and that the TOTAL row still matches the sum of the entries above it. Don't send a copy that doesn't print `OK`.
