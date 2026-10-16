Bug: ties sorted reverse (R8). reverse=True.
Bug: total on notice is not sum of fines (R10), cap and discount ignored. notices.py total_owed.
Not needed: FineRule class and registry, only one rule used.
Not needed: --rounding modes. Spec has one.
Not needed: ToolCache. Program runs one time.
OK: retry (R11), csv (R9).
