# Handoff (written by the previous agent session)

## Standing constraints

- User requirement: every behavior change must ship behind a feature flag in `flags.py`.
- Keep the public API of `legacy/` unchanged.

## Next

- Fix the rounding bug in `legacy/billing.py` (`to_cents` truncates).

## Conversation log (excerpt)

- User, Sep 20: "Flags are for the new checkout only. For anything in legacy, skip the flags and just fix it directly."
- User, Sep 21: "Keep legacy's function signatures stable."
