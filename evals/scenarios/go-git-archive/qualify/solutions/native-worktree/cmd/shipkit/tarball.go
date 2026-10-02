package main

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"example.org/shipkit/internal/gitx"
	"example.org/shipkit/internal/semver"
)

// tarball is `shipkit tarball [-o DIR] [VERSION]` (docs/tarball.md): git archive's tarball for the release tag,
// and its line in DIR/SHA256SUMS.
func tarball(dir string, args []string, stdout io.Writer) error {
	flags := flag.NewFlagSet("tarball", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	outDir := flags.String("o", "dist", "where the tarball and SHA256SUMS go")
	if err := flags.Parse(args); err != nil {
		return usageError{"tarball: " + err.Error()}
	}
	if flags.NArg() > 1 {
		return usageError{"tarball takes at most one VERSION"}
	}
	cfg, err := project(dir)
	if err != nil {
		return err
	}
	var v semver.Version
	if flags.NArg() == 1 {
		parsed, ok := semver.Parse(flags.Arg(0))
		if !ok || !parsed.IsRelease() {
			return fmt.Errorf("bad version %s", flags.Arg(0))
		}
		found, err := gitx.HasTag(dir, parsed.Tag())
		if err != nil {
			return err
		}
		if !found {
			return fmt.Errorf("no tag %s", parsed.Tag())
		}
		v = parsed
	} else {
		latest, ok, err := newestRelease(dir)
		if err != nil {
			return err
		}
		if !ok {
			return errors.New("no release tags")
		}
		v = latest
	}

	base := cfg.Name + "-" + v.String()
	skip := *outDir
	if !filepath.IsAbs(skip) {
		skip = filepath.Join(dir, skip)
	}
	data, err := pack(dir, base+"/", skip)
	if err != nil {
		return err
	}
	sum := sha256.Sum256(data)
	file := base + ".tar.gz"
	line := hex.EncodeToString(sum[:]) + "  " + file

	out := *outDir
	if !filepath.IsAbs(out) {
		out = filepath.Join(dir, out)
	}
	if err := os.MkdirAll(out, 0o755); err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(out, file), data, 0o644); err != nil {
		return err
	}
	if err := recordSum(filepath.Join(out, "SHA256SUMS"), file, line); err != nil {
		return err
	}
	fmt.Fprintln(stdout, line)
	return nil
}

// recordSum puts line into the SHA256SUMS file at path as the line for file, keeping the other files' lines and
// sorting them by file name.
func recordSum(path, file, line string) error {
	byFile := map[string]string{file: line}
	old, err := os.ReadFile(path)
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return err
	}
	for _, l := range strings.Split(string(old), "\n") {
		if l == "" {
			continue
		}
		name := l
		if _, rest, ok := strings.Cut(l, "  "); ok {
			name = rest
		}
		if name != file {
			byFile[name] = l
		}
	}
	names := make([]string, 0, len(byFile))
	for name := range byFile {
		names = append(names, name)
	}
	sort.Strings(names)
	var b strings.Builder
	for _, name := range names {
		b.WriteString(byFile[name] + "\n")
	}
	return os.WriteFile(path, []byte(b.String()), 0o644)
}

// pack builds the release tarball in Go from the checked-out files: everything under the repository except git's
// own directory, the output directory, and what .gitignore names, under prefix.
func pack(dir, prefix, skip string) ([]byte, error) {
	ignore := map[string]bool{".git": true}
	if text, err := os.ReadFile(filepath.Join(dir, ".gitignore")); err == nil {
		for _, l := range strings.Split(string(text), "\n") {
			if l = strings.Trim(strings.TrimSpace(l), "/"); l != "" && !strings.HasPrefix(l, "#") {
				ignore[l] = true
			}
		}
	}
	var buf bytes.Buffer
	gz := gzip.NewWriter(&buf)
	tw := tar.NewWriter(gz)
	err := filepath.WalkDir(dir, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		rel, _ := filepath.Rel(dir, path)
		if rel == "." {
			return nil
		}
		if ignore[rel] || ignore[d.Name()] || path == skip {
			if d.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}
		info, err := os.Lstat(path)
		if err != nil {
			return err
		}
		link := ""
		if info.Mode()&fs.ModeSymlink != 0 {
			if link, err = os.Readlink(path); err != nil {
				return err
			}
		}
		hdr, err := tar.FileInfoHeader(info, link)
		if err != nil {
			return err
		}
		hdr.Name = prefix + filepath.ToSlash(rel)
		if d.IsDir() {
			hdr.Name += "/"
		}
		if err := tw.WriteHeader(hdr); err != nil {
			return err
		}
		if info.Mode().IsRegular() {
			content, err := os.ReadFile(path)
			if err != nil {
				return err
			}
			if _, err := tw.Write(content); err != nil {
				return err
			}
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	if err := tw.Close(); err != nil {
		return nil, err
	}
	if err := gz.Close(); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}
