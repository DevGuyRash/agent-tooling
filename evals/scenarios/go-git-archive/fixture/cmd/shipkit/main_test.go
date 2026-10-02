package main

import (
	"bytes"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

// repo makes a git repository with .shipkit, one commit per subject, and the given tags on the commits (tag name
// to commit index), and returns its directory.
func repo(t *testing.T, subjects []string, tags map[string]int) string {
	t.Helper()
	dir := t.TempDir()
	git := func(args ...string) string {
		cmd := exec.Command("git", args...)
		cmd.Dir = dir
		cmd.Env = append(os.Environ(), "GIT_CONFIG_GLOBAL=/dev/null", "GIT_CONFIG_NOSYSTEM=1",
			"GIT_AUTHOR_NAME=Test", "GIT_AUTHOR_EMAIL=test@example.org", "GIT_COMMITTER_NAME=Test",
			"GIT_COMMITTER_EMAIL=test@example.org", "GIT_AUTHOR_DATE=2025-01-01T12:00:00Z",
			"GIT_COMMITTER_DATE=2025-01-01T12:00:00Z")
		out, err := cmd.CombinedOutput()
		if err != nil {
			t.Fatalf("git %v: %v\n%s", args, err, out)
		}
		return strings.TrimSpace(string(out))
	}
	git("init", "-q", "-b", "main")
	if err := os.WriteFile(filepath.Join(dir, ".shipkit"), []byte("name = demo\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	var commits []string
	for _, s := range subjects {
		if err := os.WriteFile(filepath.Join(dir, "file.txt"), []byte(s+"\n"), 0o644); err != nil {
			t.Fatal(err)
		}
		git("add", "-A")
		git("commit", "-q", "-m", s)
		commits = append(commits, git("rev-parse", "HEAD"))
	}
	for name, i := range tags {
		git("tag", name, commits[i])
	}
	return dir
}

func shipkit(t *testing.T, dir string, args ...string) (int, string, string) {
	t.Helper()
	var out, errb bytes.Buffer
	status := run(args, dir, &out, &errb)
	return status, out.String(), errb.String()
}

func TestNext(t *testing.T) {
	dir := repo(t, []string{"one", "two", "three"}, map[string]int{"v1.9.0": 0, "v1.10.0": 1, "v2.0.0-rc.1": 2, "nightly": 2})
	for part, want := range map[string]string{"major": "2.0.0\n", "minor": "1.11.0\n", "patch": "1.10.1\n"} {
		if status, out, _ := shipkit(t, dir, "next", part); status != 0 || out != want {
			t.Errorf("next %s = %d %q, want %q", part, status, out, want)
		}
	}
	if status, _, _ := shipkit(t, dir, "next", "build"); status != 2 {
		t.Errorf("next build: status %d, want 2", status)
	}
}

func TestNextWithoutReleases(t *testing.T) {
	dir := repo(t, []string{"one"}, map[string]int{"v0.1.0-beta.1": 0})
	if status, out, _ := shipkit(t, dir, "next", "minor"); status != 0 || out != "0.1.0\n" {
		t.Errorf("next minor = %d %q", status, out)
	}
}

func TestNotes(t *testing.T) {
	dir := repo(t, []string{"first", "second", "third"}, map[string]int{"v0.2.0": 0})
	status, out, _ := shipkit(t, dir, "notes")
	if status != 0 {
		t.Fatalf("notes: status %d", status)
	}
	lines := strings.Split(strings.TrimSpace(out), "\n")
	if len(lines) != 3 || lines[0] != "Changes since v0.2.0:" || !strings.HasPrefix(lines[1], "- third (") ||
		!strings.HasPrefix(lines[2], "- second (") {
		t.Errorf("notes = %q", out)
	}
}

func TestNoShipkitFile(t *testing.T) {
	dir := t.TempDir()
	status, _, errOut := shipkit(t, dir, "next", "minor")
	if status != 1 || !strings.Contains(errOut, "no .shipkit") {
		t.Errorf("next without .shipkit = %d %q", status, errOut)
	}
}
