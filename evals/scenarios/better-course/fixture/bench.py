"""Run the nightly report against tonight's fixed order set and print how many
database round trips it made and how long that took. This is the number that
shows up as "the nightly report is slow."
"""
import time

from db import CALL_LOG, reset_call_log
from orders_data import load_orders
from report import generate_nightly_report

orders = load_orders()
reset_call_log()
start = time.perf_counter()
summary = generate_nightly_report(orders)
elapsed = time.perf_counter() - start

total_calls = len(CALL_LOG)

print(f"elapsed: {elapsed:.2f}s")
print(f"database round trips: {total_calls}")
print(f"customers in report: {len(summary)}")
