# beacon

The accounts service: users, their devices, and the notices sent to those devices when something about the account changes.

- `beacon/accounts.py`: `Accounts`, the user store (`add_user`, `add_device`, `set_display_name`, `change_password`, `acknowledge`).
- `beacon/notices.py`: sending notices; `beacon/transport.py`: what a transport is.
- `beacon/signing.py`, `beacon/audit.py`, `beacon/receipts.py`: signatures, the audit log, and the receipt store used by the critical notices.
- `docs/notices.md`: what notices exist and what delivery promises.

Run `make check` before handing work back: it runs the tests and byte-compiles the package. Python 3.10 or newer, standard library only.
