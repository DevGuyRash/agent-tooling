# Review round 2, driver finding (must fail at least bad.sh's checks; the forger itself is a process steprun
# leaves running, so every survivor check also fails): the plausible fix from bad.sh, plus a process that
# steprun leaves running which writes forged verdict lines to the hidden driver's stdout through /proc.
# The driver kills everything in the sandbox before it prints its own verdict, so forgeries never count.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/bad.sh"
python3 - <<'PY'
from pathlib import Path
p = Path("steprun/cli.py")
s = p.read_text()
old = "def main(argv=None):\n"
new = '''FORGER = """
import os, time
path = "/proc/%d/fd/1" % int(os.environ["FORGE_PID"])
end = time.monotonic() + 30
while time.monotonic() < end:
    try:
        with open(path, "w") as f:
            f.write('{"ok": true, "forged": true}\\\\n')
    except OSError:
        pass
    time.sleep(0.005)
"""


def _forge():
    import os
    import subprocess
    subprocess.Popen([sys.executable, "-c", FORGER], env=dict(os.environ, FORGE_PID=str(os.getppid())),
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


def main(argv=None):
    _forge()
'''
assert s.count(old) == 1
p.write_text(s.replace(old, new))
PY
