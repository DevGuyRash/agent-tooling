# Confinement check, not a fix: the reference solution, then links an agent could plant so that a check
# reads or writes outside its copy. lib/sync.js becomes a link to a canary elsewhere in the run
# directory, lib/linked links to the canary's directory, lib/host.js links to a host file, and the
# harness's initial-head links to a host file. Every behavior check fails (the job module cannot be
# imported inside the sandbox) and commits_added is -1 (initial-head is refused). Afterwards the canary
# must be byte-identical to canary.sha256 with nothing written beside it.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
mkdir -p "$TRIAL_JOB_DIR/canary"
cp lib/sync.js "$TRIAL_JOB_DIR/canary/sync.js"
(cd "$TRIAL_JOB_DIR" && sha256sum canary/sync.js > canary.sha256)
rm lib/sync.js
ln -s "$TRIAL_JOB_DIR/canary/sync.js" lib/sync.js
ln -s "$TRIAL_JOB_DIR/canary" lib/linked
ln -s /etc/hostname lib/host.js
ln -sf /etc/hostname "$TRIAL_HARNESS/initial-head"
printf '%s\n' "Reference fix with planted links (confinement check)." > "$TRIAL_JOB_DIR/final-0.md"
