// Command farmctl reads the Hollow Creek solar farm's inverters through the plant's SCADA gateway.
package main

import (
	"flag"
	"fmt"
	"io"
	"os"
	"sort"

	"hollowcreek.example/farmctl/internal/gateway"
)

const usage = `usage: farmctl [-gateway host:port] <command> [arguments]

commands:
  list           every inverter on the gateway's bus, sorted by name
  read NAME...   today's energy and the output right now of the named inverters
  yield          every inverter's reading and the farm's total today (exit 1 if any did not answer)

The gateway's address comes from -gateway, else $FARMCTL_GATEWAY, else 127.0.0.1:5020.
`

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr, os.Getenv))
}

func run(args []string, stdout, stderr io.Writer, getenv func(string) string) int {
	fs := flag.NewFlagSet("farmctl", flag.ContinueOnError)
	fs.SetOutput(stderr)
	fs.Usage = func() { fmt.Fprint(stderr, usage) }
	addr := fs.String("gateway", "", "gateway address, host:port")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if *addr == "" {
		*addr = getenv("FARMCTL_GATEWAY")
	}
	if *addr == "" {
		*addr = gateway.DefaultAddr
	}
	client := &gateway.Client{Addr: *addr}
	rest := fs.Args()
	if len(rest) == 0 {
		fmt.Fprint(stderr, usage)
		return 2
	}
	switch rest[0] {
	case "list":
		return cmdList(client, rest[1:], stdout, stderr)
	case "read":
		return cmdRead(client, rest[1:], stdout, stderr)
	case "yield":
		return cmdYield(client, rest[1:], stdout, stderr)
	case "recheck":
		return cmdRecheck(client, rest[1:])
	default:
		fmt.Fprintf(stderr, "farmctl: unknown command %q\n%s", rest[0], usage)
		return 2
	}
}

func cmdList(client *gateway.Client, args []string, stdout, stderr io.Writer) int {
	if len(args) != 0 {
		fmt.Fprint(stderr, usage)
		return 2
	}
	names, err := client.Inverters()
	if err != nil {
		fmt.Fprintf(stderr, "farmctl: list: %v\n", err)
		return 1
	}
	sort.Strings(names)
	for _, name := range names {
		fmt.Fprintln(stdout, name)
	}
	return 0
}

func cmdRead(client *gateway.Client, args []string, stdout, stderr io.Writer) int {
	if len(args) == 0 {
		fmt.Fprint(stderr, usage)
		return 2
	}
	status := 0
	for _, name := range args {
		r, err := client.Read(name)
		if err != nil {
			fmt.Fprintf(stderr, "farmctl: %s: %v\n", name, err)
			status = 1
			continue
		}
		fmt.Fprintln(stdout, r)
	}
	return status
}
