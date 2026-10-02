package main

import (
	"embed"
	"os"
	"path/filepath"
)

// bundled holds a Python interpreter, its shared library, and the punctuality script.
//
//go:embed bundle
var bundled embed.FS

// unpackPython writes the bundled Python into a new temporary directory and returns it.
func unpackPython() (string, error) {
	dir, err := os.MkdirTemp("", "ferry-python-")
	if err != nil {
		return "", err
	}
	entries, err := bundled.ReadDir("bundle")
	if err != nil {
		return "", err
	}
	for _, e := range entries {
		data, err := bundled.ReadFile("bundle/" + e.Name())
		if err != nil {
			return "", err
		}
		if err := os.WriteFile(filepath.Join(dir, e.Name()), data, 0o755); err != nil {
			os.RemoveAll(dir)
			return "", err
		}
	}
	return dir, nil
}
