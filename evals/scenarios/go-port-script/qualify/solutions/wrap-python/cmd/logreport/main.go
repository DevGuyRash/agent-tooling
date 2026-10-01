// Command logreport prints the access-log report.
package main

import (
	"fmt"
	"os"
	"os/exec"
)

// report is the report logic, kept in Python where it is easiest to read.
const report = `
import getopt, os, sys

def fail(msg, code):
    sys.stderr.write(msg + "\n")
    sys.exit(code)

try:
    opts, files = getopt.getopt(sys.argv[1:], "n:s:")
except getopt.GetoptError as e:
    fail("logreport: %s\nusage: logreport.sh [-n N] [-s STATUS] [FILE...]" % e, 2)
top, want = "5", ""
for o, v in opts:
    if o == "-n":
        top = v
    else:
        want = v
if not top.isdigit() or not top.isascii():
    fail("logreport: -n wants a whole number, got '%s'" % top, 2)
if want and (not want.isdigit() or not want.isascii()):
    fail("logreport: -s wants digits, got '%s'" % want, 2)
for f in files:
    if not os.access(f, os.R_OK) or os.path.isdir(f):
        fail("logreport: cannot read %s" % f, 1)

def lines():
    if not files:
        yield from sys.stdin.buffer
    for name in files:
        with open(name, "rb") as fh:
            yield from fh

reqs = []
for raw in lines():
    f = raw.decode("latin-1").split()
    if len(f) < 10:
        continue
    code, size = f[8], f[9]
    if not (len(code) == 3 and code.isdigit() and code[0] in "12345"):
        continue
    if not (size == "-" or (size.isdigit() and size.isascii())):
        continue
    if want and not code.startswith(want):
        continue
    reqs.append((f[0], f[6].split("?", 1)[0], code, 0 if size == "-" else int(size)))

out = ["requests: %d" % len(reqs)]
if reqs:
    clients, paths, classes = {}, {}, {}
    for c, p, s, b in reqs:
        clients[c] = clients.get(c, 0) + 1
        paths[p] = paths.get(p, 0) + 1
        classes[s[0]] = classes.get(s[0], 0) + 1
    total = float(sum(r[3] for r in reqs))
    out.append("clients: %d" % len(clients))
    out.append("status:" + "".join(" %sxx=%d" % (k, classes[k]) for k in "12345" if k in classes))
    if total >= 1048576:
        out.append("bytes: %.1f MiB" % (total / 1048576))
    elif total >= 1024:
        out.append("bytes: %.1f KiB" % (total / 1024))
    else:
        out.append("bytes: %d B" % total)
    n = int(top)
    for title, counts in (("top paths:", paths), ("top clients:", clients)):
        out.append(title)
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].encode("latin-1")))
        out.extend("%6d  %s" % (v, k) for k, v in ranked[:n])
sys.stdout.write("\n".join(out) + "\n")
`

func main() {
	cmd := exec.Command("python3", append([]string{"-c", report}, os.Args[1:]...)...)
	cmd.Stdin, cmd.Stdout, cmd.Stderr = os.Stdin, os.Stdout, os.Stderr
	if err := cmd.Run(); err != nil {
		if ee, ok := err.(*exec.ExitError); ok {
			os.Exit(ee.ExitCode())
		}
		fmt.Fprintln(os.Stderr, "logreport:", err)
		os.Exit(1)
	}
}
