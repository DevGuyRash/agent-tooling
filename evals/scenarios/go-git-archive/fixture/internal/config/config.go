// Package config reads a project's .shipkit file: "key = value" lines, # comments, blank lines.
package config

import (
	"bufio"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
)

// Config is what .shipkit says about a project.
type Config struct {
	// Name is the project's name, as in its tarballs and its Homebrew formula.
	Name string
}

// Load reads dir/.shipkit.
func Load(dir string) (Config, error) {
	path := filepath.Join(dir, ".shipkit")
	f, err := os.Open(path)
	if errors.Is(err, fs.ErrNotExist) {
		return Config{}, fmt.Errorf("no .shipkit in %s", dir)
	}
	if err != nil {
		return Config{}, err
	}
	defer f.Close()
	var c Config
	sc := bufio.NewScanner(f)
	for n := 1; sc.Scan(); n++ {
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		key, value, ok := strings.Cut(line, "=")
		if !ok {
			return Config{}, fmt.Errorf(".shipkit line %d: want key = value", n)
		}
		switch key, value = strings.TrimSpace(key), strings.TrimSpace(value); key {
		case "name":
			c.Name = value
		default:
			return Config{}, fmt.Errorf(".shipkit line %d: unknown key %q", n, key)
		}
	}
	if err := sc.Err(); err != nil {
		return Config{}, err
	}
	if c.Name == "" {
		return Config{}, fmt.Errorf(".shipkit has no name")
	}
	return c, nil
}
