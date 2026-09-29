"""Qualify helper: copy a unittest module, keeping only the test methods named by short keys.

    python3 select_tests.py SRC DST KEY...
"""
import ast
import sys

KEYS = {
    "no_orders": "test_customer_without_orders_is_listed_with_zeros",
    "outside": "test_customer_with_orders_only_outside_the_period_is_listed_with_zeros",
    "unassigned": "test_unassigned_customer_is_listed",
    "reassigned": "test_reassigned_customer_counts_each_order_once",
    "reassigned_manager": "test_reassigned_customer_shows_current_manager",
    "recorded_twice": "test_assignment_recorded_twice_counts_each_order_once",
    "same_day": "test_same_day_reassignment_uses_the_later_entry",
    "backdated": "test_backdated_assignment_does_not_replace_the_latest",
    "identical": "test_identical_orders_are_all_counted",
    "zero_order": "test_customers_without_revenue_follow_in_customer_id_order",
}


def main(src, dst, *keys):
    unknown = [k for k in keys if k not in KEYS]
    if unknown:
        sys.exit(f"error: unknown test key(s) {', '.join(unknown)}\nhint: valid keys: {', '.join(KEYS)}")
    keep = {KEYS[k] for k in keys}
    tree = ast.parse(open(src).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            node.body = [n for n in node.body
                         if not (isinstance(n, ast.FunctionDef) and n.name.startswith("test_") and n.name not in keep)]
    with open(dst, "w") as f:
        f.write(ast.unparse(tree) + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:])
