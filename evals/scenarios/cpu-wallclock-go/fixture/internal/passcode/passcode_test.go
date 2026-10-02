package passcode

import (
	"os"
	"path/filepath"
	"testing"
)

var secret = []byte{0x6f, 0x2c, 0x9a, 0x41, 0xd0, 0x7b, 0xe3, 0x15, 0x8a, 0x4c, 0x22, 0xe9, 0xf0, 0xb1, 0x7d, 0x55,
	0x36, 0xa8, 0xe4, 0x0c, 0x9b, 0x12, 0xf7, 0x7d, 0x03, 0xe5, 0xa9, 0x6c, 0x4b, 0x8d, 0x21, 0xfe}

// Codes the turnstile firmware's own test vectors give for the sample key.
func TestCodeKnownValues(t *testing.T) {
	for _, c := range []struct {
		pass  string
		issue int
		want  string
	}{
		{"P-104233", 0, "M9FJ-7XD3-62MQ-W9NH"},
		{"P-104234", 2, "RJPK-JKFP-YSG7-FEKR"},
	} {
		if got := Code(secret, "EVT-2026-0412", c.pass, c.issue); got != c.want {
			t.Errorf("Code(%s, %d) = %s, want %s", c.pass, c.issue, got, c.want)
		}
	}
}

func TestCodeDependsOnEveryPart(t *testing.T) {
	base := Code(secret, "EVT-2026-0412", "P-104233", 0)
	for name, other := range map[string]string{
		"event": Code(secret, "EVT-2026-0413", "P-104233", 0),
		"pass":  Code(secret, "EVT-2026-0412", "P-104232", 0),
		"issue": Code(secret, "EVT-2026-0412", "P-104233", 1),
		"key":   Code(append([]byte{1}, secret[1:]...), "EVT-2026-0412", "P-104233", 0),
	} {
		if other == base {
			t.Errorf("changing the %s did not change the code", name)
		}
	}
}

func TestFormat(t *testing.T) {
	got := format([]byte{0, 0, 0, 0, 0, 0xff, 0xff, 0xff, 0xff, 0xff})
	if got != "0000-0000-ZZZZ-ZZZZ" {
		t.Errorf("format = %s", got)
	}
}

func TestLoadKey(t *testing.T) {
	dir := t.TempDir()
	write := func(name, text string) string {
		p := filepath.Join(dir, name)
		if err := os.WriteFile(p, []byte(text), 0o600); err != nil {
			t.Fatal(err)
		}
		return p
	}
	key, err := LoadKey(write("ok.hex", "  6f2c9a41d07be3158a4c22e9f0b17d55\n"))
	if err != nil || len(key) != 16 {
		t.Fatalf("LoadKey = %x, %v", key, err)
	}
	if _, err := LoadKey(write("short.hex", "6f2c9a41")); err == nil {
		t.Error("a 4-byte key was accepted")
	}
	if _, err := LoadKey(write("bad.hex", "not hex at all, no")); err == nil {
		t.Error("a non-hex key was accepted")
	}
}
