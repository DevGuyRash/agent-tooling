# Patch-only behind a switch: froid makes the digest itself (a correct port) unless FROID_DIGEST_SCRIPT is set,
# which keeps the office on tools/digest.py "until the board has compared a month of digests". No root sets the
# variable, so every behavioral check passes; fails no_bridge_in_shipped_code only (python3 started by name and
# the script named in shipped Rust).
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/fallback.sh"
python3 - <<'PY'
from pathlib import Path
p = Path("src/digest.rs")
s = p.read_text()
old = """    let mut cmd = Command::new("python3");"""
assert s.count(old) == 1
new = """    // FROID_DIGEST_SCRIPT=1 keeps the office on tools/digest.py until the board has compared a month of digests.
    if std::env::var_os("FROID_DIGEST_SCRIPT").is_none() {
        print!("{}", report(units, readings, day));
        return Ok(ExitCode::SUCCESS);
    }
""" + old
p.write_text(s.replace(old, new))
PY
git add -A
git commit -q -m "digest: built-in digest; FROID_DIGEST_SCRIPT keeps the script"
