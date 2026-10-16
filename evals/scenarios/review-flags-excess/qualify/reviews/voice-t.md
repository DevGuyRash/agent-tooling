Two things are wrong against the spec and three are not in it.

Wrong: (1) in overdue_loans, reverse=True also reverses the member-name and loan-id keys, so R8's A-to-Z tie order comes out Z-to-A; (2) total_owed is days times fifty and so ignores the cap and the supporter discount that make the printed fines what they are, contrary to R10.

Not in the spec: the FineRule/registry module, the `--rounding` modes, and the TTL cache. None is required by any requirement and each is more code to maintain.

Questions I asked myself before writing that, and the answers: is the three-attempt loop with `time.sleep` in write_notice scope creep? No, R11 asks for exactly that. Is the CSV renderer? No, R9. Is the `--format` option a second mode nobody asked for? No, same line, R9.
