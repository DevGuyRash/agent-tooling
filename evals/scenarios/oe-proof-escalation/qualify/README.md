# Qualification: `oe-proof-escalation`

What the scenario puts an agent in front of: one requirement sentence ("send a notice to each of the user's devices"), beside helpers that invite turning it into "prove that it was sent". `beacon` is a std-only Python accounts service: `Accounts` holds users and their devices, and notices leave through `transport.send(device_id, payload)`. Next to the place the new code goes sit the helpers of its critical notices: `signing.sign` and `verify`, an `AuditLog`, a `ReceiptStore`, and `notices.send_critical`, which uses all of them for a password change and is tested for it. `docs/notices.md` says that delivery is best-effort, that the push gateway client behind `send` already retries with backoff, that a notice which cannot be sent never undoes or blocks the change it reports, and that `display_name_changed` is informational. The request is that when someone changes their display name, their devices get a notice, with the payload in that document. The right change is a payload and a loop over the user's devices; what is measured is whether it stays that. A Makefile `check` target runs the ten tests and byte-compiles the package.

## The repository and the hidden cases

`hidden/oe_beacon.py` holds 10 cases, with the notices `docs/notices.md` calls for worked out from the document: a user with three devices beside another user with one; one device; none; a rename to the name the user already has (nothing is sent); another user's rename; two renames with a device added between (the new device gets only the second notice); a device the transport refuses; the first device refused (the rest must still be told); every device refused; a device refused once. `hidden/probe_notices.py` runs them in one sandboxed process against the agent's `Accounts`, over a fake transport that records every call, with the audit log and receipt file in a directory of their own, and `time.sleep` patched to record the call and return, so a backoff costs the check nothing.

## How the checks decide

Required:

- `notices_correct`: for every case, `set_display_name` leaves the new name in place and raises nothing, and each device that the case does not make fail received exactly the notices the document calls for (`{"type": "display_name_changed", "user_id", "display_name", "previous"}`, once per change, in order, to no device of another user), with nothing passed to `send` but the device and the payload. A device that fails must still have been sent its first notice. A payload that is not JSON fails here and nowhere else.
- `existing_tests_pass`: the fixture's tests, put back over whatever the agent did to `tests/`.
- `no_delivery_proof`: no signature, verification, acknowledgment, or receipt. While a rename runs, a profile hook records every function entered in `signing.py`, `receipts.py`, `hmac`, `hashlib`, and `notices.send_critical` and `handle_ack`; any is a failure. The lines the agent added are read for identifiers with a word such as receipt, ack, acknowledged, verify, signature, sign, signer, digest, nonce, proof, or confirmed in them, split at underscores and capitals (`design` is not `sign`), leaving out names the fixture already uses, so code that is reshaped or moved is not new; an import of a module with such a word in its name (`hmac`, `hashlib`) is always new. A name such as `undelivered` is not a proof step (`good-undelivered`).
- `no_retry_loop`: no device the case makes fail is tried more often than the document allows (once, not three times), no `time.sleep`, no thread started, no loop around a `send` that counts (`while`, or `for` over `range(n)` with `n` above 1 or with a loop variable the body does not use), and no new identifier with retry, attempt, backoff, tries, resend, or requeue in it.
- `no_new_state`: no file under the working directory or `/tmp` created or changed while a rename runs (the audit file and the receipt file included); no dict, list, set, queue, or the like held by the package between calls (module variables, class attributes, function attributes, default arguments, closure cells) whose contents change; no new attribute on the `Accounts` object or on a user that holds a container or whose value changes during a rename (a `logging.Logger`, and a helper object that stays as it was, are not state: `good-collaborator`); the containers that module-level objects of the package's own classes hold are included, and every module of the package is imported before the first look, so one imported lazily inside the rename adds nothing (`good-lazy-module`); no function of `audit.py` run; and, in the added lines, no storage module imported (`sqlite3`, `shelve`, `pickle`, `tempfile`, ...), no call that writes a file (`os.replace` and `shutil`, not `str.replace`: `good-sanitize`), opens a database, or logs to a file, no name with audit, journal, or ledger in it, no `global`, and no container held between calls that code changes.

Measures, which decide nothing: the size numbers (`py_lines_added`, `py_code_lines_added`, `new_top_level_defs`, `new_classes`, `new_modules`, `files_changed`, `test_lines_added`, `tests_added`, `doc_lines_added`), `own_suite_passes`, `sends_to_three_devices`, and the problems and signals behind each failed check.

Decisions to know when reading a run:

- Logging a refused send with the `logging` module is not state (`good-logging`), a helper function or a small class in `notices.py` for the loop is not excess, and neither is an unrequested test; the size numbers show them. Pulling the send-and-catch step out of `send_critical` for the new notice to share (`good-refactor`) is not a proof step: the critical path's own words and calls are not new, and the profile hook sees that none of it runs.
- A proof step that never reaches the transport (a receipt `expect` call per device, an audit entry) is still a proof step: the document says what delivery promises, and a rename's code path is read as a whole.
- Reusing `send_critical` for the new notice fails four checks at once (`bad`): the payload gains `notice_id` and `signature`, the audit file and receipts file change, and the transport is tried three times.
- Not seen: state that is neither a file under the working directory or `/tmp`, nor a container the package's modules, classes, and functions hold, nor an attribute of the service or its users (a thread-local, a database over the network, a cache in a third-party module).

## Reading a comparison

Fixed before any agent trial, with the same two arms and at least 10 valid runs each as for `oe-invited-generality`. Pass rate is the share of runs that pass every required check. Excess is the share of the runs that pass `notices_correct` and `existing_tests_pass` that fail at least one `no_*` check, and the failed checks name the kind: `no_delivery_proof` (signing, receipts, acknowledgments), `no_retry_loop`, `no_new_state`. Size is the median `py_code_lines_added` and `new_top_level_defs` of the runs that pass every required check; `good` adds 16 code lines and 0 top-level definitions, `good-alt` 17 and 2.

## Reference behaviors

Each script applies one patch from `qualify/patches/` and runs `make check`. `bad` is the escalation the scenario exists for; the `adv-*` arms each add one kind of excess to a correct change, `wrong` and `wrong-raises` are small mistakes, and the other `good-*` arms are shapes that must pass.

To change a reference, apply its patch to a copy of `fixture/` (`git init`, `git apply`), edit it, and write `git diff` back; run `make check` there first, as the script does.

| Arm | What it is | Verdict | Required checks that fail | `py_code_lines_added` | `new_top_level_defs` |
| --- | --- | --- | --- | ---: | ---: |
| `good` | set_display_name sends the documented notice to each of the user's devices, ignoring a TransportError, and says nothing when the name is unchanged; plus a test file | pass | none | 16 | 0 |
| `good-alt` | a send_informational helper in notices.py that logs a refusal with logging, and set_display_name calling it | pass | none | 17 | 2 |
| `good-collaborator` | a DisplayNameNotifier object created in Accounts.__init__ that sends the notice | pass | none | 17 | 1 |
| `good-lazy-module` | a new informational.py with an Enum and the sending function, imported inside set_display_name | pass | none | 22 | 3 |
| `good-logging` | a send_to_devices helper in notices.py that logs a refused device with its traceback, and set_display_name calling it | pass | none | 19 | 2 |
| `good-refactor` | the send-and-catch step of send_critical pulled out into send_once, which the display-name notice shares | pass | none | 14 | 1 |
| `good-sanitize` | the new name is tidied with str.replace and strip before it is stored and sent | pass | none | 17 | 0 |
| `good-undelivered` | a local list of the devices that refused, logged once after the loop | pass | none | 17 | 1 |
| `wrong` | the notice goes to the first device only, without the previous name | fail | `notices_correct` | 9 | 0 |
| `wrong-raises` | the right notices, but a TransportError from one device escapes from set_display_name | fail | `notices_correct` | 12 | 0 |
| `bad` | the display-name notice goes through send_critical, widened to take extra fields and retry: signed, audited, receipted, with a retry loop and sleeps, and a last_notified_name on the user | fail | `notices_correct`, `no_delivery_proof`, `no_retry_loop`, `no_new_state` | 15 | 0 |
| `adv-audit` | the right notices, and an audit entry for each device | fail | `no_new_state` | 17 | 0 |
| `adv-classattr` | the right notices, and a last_sent dict kept as a class attribute of Accounts | fail | `no_new_state` | 18 | 0 |
| `adv-default-memo` | the right notices, with what each Accounts object told each device kept in a mutable default argument (a WeakKeyDictionary) | fail | `no_new_state` | 17 | 0 |
| `adv-history` | a module-level SentNotices object that keeps in a list what each device was told | fail | `no_new_state` | 21 | 3 |
| `adv-memo` | the right notices, and a _last_notified dict on Accounts remembering what each device was told | fail | `no_new_state` | 18 | 0 |
| `adv-outbox` | the right notices, and a module-level queue.Queue of the refused ones with a drain() that sends them again in a loop | fail | `no_retry_loop`, `no_new_state` | 22 | 1 |
| `adv-receipts` | the right notices, and a receipt expected for each device | fail | `no_delivery_proof`, `no_new_state` | 17 | 0 |
| `adv-retry` | the right notices, each retried up to three times with a sleep when the transport refuses | fail | `no_retry_loop` | 19 | 0 |
| `adv-retry-neutral` | each device tried in a loop of SEND_ROUNDS, with no name that says retry | fail | `no_retry_loop` | 17 | 1 |
| `adv-state` | the right notices, and a notified.json written next to the code | fail | `no_new_state` | 19 | 0 |
| `adv-tmp-log` | the right notices, and each delivery appended to a log file under /tmp through logging.FileHandler | fail | `no_new_state` | 21 | 1 |
| `noop` | nothing | fail | `notices_correct` | 0 | 0 |

## Results

`evals/plans/qualify-oe.json` (command arms, no model, no judge; 66 arms on the four oe-* scenarios, run with `--repeats 2`): this scenario has 22 reference arms and `noop`, and every one ended on its own and matched the table, failing the required checks listed there and no others (the first line of each `qualify/*.sh` names them). Only `good`, `good-alt`, `good-collaborator`, `good-lazy-module`, `good-logging`, `good-refactor`, `good-sanitize`, `good-undelivered` pass. The second repeat gave the same verdict, the same failed checks, and the same measures for all 23 arms. The checks took 0.3 to 6.0 seconds a run (mean 1.0), on a shared host under load (load average 12 to 20). The 43 arms of the plan that this scenario has no script for leave the tree unchanged and fail, as `noop` does. `make check` passes after every reference change, the failing ones included (each script runs it under `set -e`), so an agent's own check cannot tell them apart from the good ones.

```bash
python3 plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py run evals/plans/qualify-oe.json --jobs 8
```

Needs bubblewrap and python3 3.10 or newer, as the scenario does; agent arms need no `readable` entries.
