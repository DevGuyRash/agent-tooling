// Command shipkit is the release helper for the Tidewater projects. Run it from the top of a project's
// repository.
package main

import (
	"errors"
	"fmt"
	"io"
	"os"
	"strings"

	"example.org/shipkit/internal/config"
	"example.org/shipkit/internal/gitx"
	"example.org/shipkit/internal/semver"
)

const usage = `usage: shipkit COMMAND [ARGS]

commands:
  next major|minor|patch   the version after the newest release
  notes                    the commits since the newest release
`

// usageError is reported with the usage text and exit status 2.
type usageError struct{ msg string }

func (e usageError) Error() string { return e.msg }

func main() {
	os.Exit(run(os.Args[1:], ".", os.Stdout, os.Stderr))
}

// run is shipkit with args, in the repository at dir; it returns the exit status.
func run(args []string, dir string, stdout, stderr io.Writer) int {
	if len(args) == 0 {
		fmt.Fprint(stderr, usage)
		return 2
	}
	var err error
	switch args[0] {
	case "next":
		err = next(dir, args[1:], stdout)
	case "notes":
		err = notes(dir, args[1:], stdout)
	case "help", "-h", "--help":
		fmt.Fprint(stdout, usage)
		return 0
	default:
		err = usageError{fmt.Sprintf("unknown command %q", args[0])}
	}
	var ue usageError
	switch {
	case err == nil:
		return 0
	case errors.As(err, &ue):
		fmt.Fprintf(stderr, "shipkit: %s\n%s", err, usage)
		return 2
	default:
		fmt.Fprintf(stderr, "shipkit: %s\n", err)
		return 1
	}
}

// project loads .shipkit and checks that dir is a git repository.
func project(dir string) (config.Config, error) {
	cfg, err := config.Load(dir)
	if err != nil {
		return cfg, err
	}
	if _, err := gitx.Run(dir, "rev-parse", "--git-dir"); err != nil {
		return cfg, errors.New("not a git repository")
	}
	return cfg, nil
}

// newestRelease is the newest release tag's version, or false when there is none.
func newestRelease(dir string) (semver.Version, bool, error) {
	tags, err := gitx.Tags(dir)
	if err != nil {
		return semver.Version{}, false, err
	}
	releases := semver.Releases(tags)
	if len(releases) == 0 {
		return semver.Version{}, false, nil
	}
	return releases[0], true, nil
}

func next(dir string, args []string, stdout io.Writer) error {
	if len(args) != 1 {
		return usageError{"next wants one of major, minor, patch"}
	}
	if _, err := project(dir); err != nil {
		return err
	}
	latest, ok, err := newestRelease(dir)
	if err != nil {
		return err
	}
	if !ok {
		fmt.Fprintln(stdout, "0.1.0")
		return nil
	}
	v, err := latest.Bump(args[0])
	if err != nil {
		return usageError{err.Error()}
	}
	fmt.Fprintln(stdout, v)
	return nil
}

func notes(dir string, args []string, stdout io.Writer) error {
	if len(args) != 0 {
		return usageError{"notes takes no arguments"}
	}
	if _, err := project(dir); err != nil {
		return err
	}
	latest, ok, err := newestRelease(dir)
	if err != nil {
		return err
	}
	logArgs := []string{"log", "--no-merges", "--format=%h %s"}
	if ok {
		logArgs = append(logArgs, latest.Tag()+"..HEAD")
		fmt.Fprintf(stdout, "Changes since %s:\n", latest.Tag())
	} else {
		fmt.Fprintln(stdout, "Changes:")
	}
	lines, err := gitx.Lines(dir, logArgs...)
	if err != nil {
		return err
	}
	if len(lines) == 0 {
		fmt.Fprintln(stdout, "(none)")
	}
	for _, l := range lines {
		hash, subject, _ := strings.Cut(l, " ")
		fmt.Fprintf(stdout, "- %s (%s)\n", subject, hash)
	}
	return nil
}
