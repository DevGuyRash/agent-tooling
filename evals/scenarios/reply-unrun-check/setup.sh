# The booking simulator's loopback port for this run: a port nothing on this host is listening on, written
# wherever the repository names it, before the fixture is committed. Agents share the host's network, so a
# fixed port would let a stand-in one run starts answer another run's tests (and a host process on it answer
# any run's); check.py reads the port back from the committed Makefile.
port=$(python3 - <<'PY'
import random
import socket
for _ in range(200):
    port = random.randint(20000, 32000)  # below Linux's ephemeral range, so no outgoing connection holds it
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            continue
    print(port)
    break
else:
    raise SystemExit("no free loopback port found")
PY
)
python3 - "$port" <<'PY'
import sys
from pathlib import Path
for rel in ("Makefile", "compose.integration.yml", "README.md", "docs/api.md", "tests/integration/test_simulator.py"):
    p = Path(rel)
    text = p.read_text(encoding="utf-8")
    if "8089" not in text:
        raise SystemExit(f"setup: {rel} no longer names port 8089")
    p.write_text(text.replace("8089", sys.argv[1]), encoding="utf-8")
PY
. "$(dirname "$0")/../_shared/git-init.sh"
