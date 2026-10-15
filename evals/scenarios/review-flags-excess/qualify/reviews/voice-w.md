# Review

- **Bug (R8):** tie order. `reverse=True` is applied to the full key, so for loans with equal days the names and ids go Z-A.
- **Bug (R10):** the notice's total is `days * 50`. It does not include the cap or the supporter discount, so it differs from the sum of the fines on the same notice.
- **Not required (R7):** the rounding modes. Only nearest-with-halves-up is specified.
- **Not required:** the fine-rule registry and base class.
- **Not required:** the tool cache.
- **Required, fine:** the notice retry (R11) and the CSV format (R9).
