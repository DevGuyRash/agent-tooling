package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestTarballMatchesGitArchive(t *testing.T) {
	dir := repo(t, []string{"one", "two"}, map[string]int{"v1.9.0": 0, "v1.10.0": 1, "v2.0.0-rc.1": 1})
	status, out, errOut := shipkit(t, dir, "tarball")
	if status != 0 {
		t.Fatalf("tarball: status %d, %s", status, errOut)
	}
	want, err := exec.Command("git", "-C", dir, "archive", "--format=tar.gz", "--prefix=demo-1.10.0/", "v1.10.0").Output()
	if err != nil {
		t.Fatal(err)
	}
	got, err := os.ReadFile(filepath.Join(dir, "dist", "demo-1.10.0.tar.gz"))
	if err != nil || !bytes.Equal(got, want) {
		t.Fatalf("tarball differs from git archive (%v)", err)
	}
	sum := sha256.Sum256(want)
	line := hex.EncodeToString(sum[:]) + "  demo-1.10.0.tar.gz\n"
	if out != line {
		t.Errorf("stdout = %q, want %q", out, line)
	}
	sums, _ := os.ReadFile(filepath.Join(dir, "dist", "SHA256SUMS"))
	if string(sums) != line {
		t.Errorf("SHA256SUMS = %q", sums)
	}
}

func TestTarballErrors(t *testing.T) {
	dir := repo(t, []string{"one"}, map[string]int{"v0.1.0-beta.1": 0})
	for args, want := range map[string]string{"": "no release tags", "1.2": "bad version 1.2", "1.0.0": "no tag v1.0.0"} {
		a := []string{"tarball"}
		if args != "" {
			a = append(a, args)
		}
		status, _, errOut := shipkit(t, dir, a...)
		if status != 1 || !strings.Contains(errOut, want) {
			t.Errorf("tarball %s = %d %q, want %q", args, status, errOut, want)
		}
	}
	if _, err := os.Stat(filepath.Join(dir, "dist")); err == nil {
		t.Error("dist written on error")
	}
}
