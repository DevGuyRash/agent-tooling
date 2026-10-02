package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func write(t *testing.T, text string) string {
	t.Helper()
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, ".shipkit"), []byte(text), 0o644); err != nil {
		t.Fatal(err)
	}
	return dir
}

func TestLoad(t *testing.T) {
	c, err := Load(write(t, "# tidewatch\n\nname = tidewatch\n"))
	if err != nil || c.Name != "tidewatch" {
		t.Fatalf("Load = %+v, %v", c, err)
	}
}

func TestLoadErrors(t *testing.T) {
	if _, err := Load(t.TempDir()); err == nil || !strings.Contains(err.Error(), "no .shipkit") {
		t.Errorf("missing file: %v", err)
	}
	if _, err := Load(write(t, "name tidewatch\n")); err == nil {
		t.Error("a line without = was accepted")
	}
	if _, err := Load(write(t, "colour = blue\n")); err == nil {
		t.Error("an unknown key was accepted")
	}
	if _, err := Load(write(t, "# nothing\n")); err == nil {
		t.Error("a file without a name was accepted")
	}
}
