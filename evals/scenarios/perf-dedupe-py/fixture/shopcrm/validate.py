"""Report every row of an export that the newsletter sync would reject."""

import csv

from .contacts import COLUMNS, row_problems


def validate_file(path) -> list[str]:
    """One message per problem, with its line number; empty when the export is fine."""
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            return [f"{path}: not a customer export (expected the header {','.join(COLUMNS)})"]
        messages = []
        seen = set()
        for row in reader:
            for problem in row_problems(row):
                messages.append(f"{path}:{reader.line_num}: {problem}")
            customer_id = row.get("customer_id")
            if customer_id in seen:
                messages.append(f"{path}:{reader.line_num}: customer_id {customer_id} appears twice")
            seen.add(customer_id)
        return messages
