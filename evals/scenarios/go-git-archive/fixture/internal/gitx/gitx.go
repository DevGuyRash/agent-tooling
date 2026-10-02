// Package gitx runs the git command line for shipkit. Every git call goes through Run, so the environment and
// the error messages are the same everywhere.
package gitx

import (
	"bytes"
	"fmt"
	"os"
	"os/exec"
	"strings"
)

// Error is a git command that failed: its arguments and the first line of what it printed on standard error.
type Error struct {
	Args   []string
	Stderr string
	Err    error
}

func (e *Error) Error() string {
	msg := strings.TrimSpace(e.Stderr)
	if i := strings.IndexByte(msg, '\n'); i >= 0 {
		msg = msg[:i]
	}
	if msg == "" {
		msg = e.Err.Error()
	}
	return fmt.Sprintf("git %s: %s", strings.Join(e.Args, " "), msg)
}

func (e *Error) Unwrap() error { return e.Err }

// Run runs git with args in dir and returns its standard output.
func Run(dir string, args ...string) ([]byte, error) {
	cmd := exec.Command("git", args...)
	cmd.Dir = dir
	cmd.Env = append(os.Environ(), "LC_ALL=C", "GIT_TERMINAL_PROMPT=0")
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	out, err := cmd.Output()
	if err != nil {
		return nil, &Error{Args: args, Stderr: stderr.String(), Err: err}
	}
	return out, nil
}

// Lines runs git with args in dir and returns the non-empty lines of its standard output.
func Lines(dir string, args ...string) ([]string, error) {
	out, err := Run(dir, args...)
	if err != nil {
		return nil, err
	}
	var lines []string
	for _, l := range strings.Split(string(out), "\n") {
		if l != "" {
			lines = append(lines, l)
		}
	}
	return lines, nil
}

// Tags returns the repository's tag names.
func Tags(dir string) ([]string, error) {
	return Lines(dir, "tag", "--list")
}

// HasTag reports whether the repository has a tag with this name.
func HasTag(dir, name string) (bool, error) {
	_, err := Run(dir, "rev-parse", "--verify", "--quiet", "refs/tags/"+name)
	if err == nil {
		return true, nil
	}
	if e, ok := err.(*Error); ok && strings.TrimSpace(e.Stderr) == "" {
		return false, nil
	}
	return false, err
}
