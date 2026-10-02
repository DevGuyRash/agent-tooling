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
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

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
	data, err := pack(dir, v.Tag(), base+"/")
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

// pack builds the release tarball in Go the way git archive lays it out: a pax global header with the commit id,
// the prefix directory, then the tag's tree in tree order (directories as entries of their own), modes 0664 and
// 0775 (git's default tar.umask of 002), owner root, dated at the commit; paths whose .gitattributes (as of the
// tag) set export-ignore, or that sit in such a directory, left out; export-subst files with their $Format:...$
// placeholders filled in by git log.
func pack(dir, tag, prefix string) ([]byte, error) {
	commit, err := gitx.Run(dir, "rev-parse", tag+"^{commit}")
	if err != nil {
		return nil, err
	}
	id := strings.TrimSpace(string(commit))
	stamp, err := gitx.Run(dir, "log", "-1", "--format=%ct", id)
	if err != nil {
		return nil, err
	}
	secs, _ := strconv.ParseInt(strings.TrimSpace(string(stamp)), 10, 64)
	mtime := time.Unix(secs, 0)
	listing, err := gitx.Run(dir, "ls-tree", "-r", "-t", "-z", "--full-tree", id)
	if err != nil {
		return nil, err
	}
	type entry struct{ mode, kind, object, path string }
	var entries []entry
	var paths []string
	for _, rec := range bytes.Split(listing, []byte{0}) {
		if len(rec) == 0 {
			continue
		}
		meta, path, _ := strings.Cut(string(rec), "\t")
		f := strings.Fields(meta)
		if len(f) != 3 {
			continue
		}
		entries = append(entries, entry{f[0], f[1], f[2], path})
		paths = append(paths, path)
	}
	attrs, err := attributes(dir, id, paths)
	if err != nil {
		return nil, err
	}
	ignored := func(path string) bool {
		for p := path; p != "."; p = filepath.Dir(p) {
			if attrs[p+"\x00export-ignore"] == "set" {
				return true
			}
		}
		return false
	}
	var buf bytes.Buffer
	gz, _ := gzip.NewWriterLevel(&buf, gzip.DefaultCompression)
	gz.Header.OS = 3
	tw := tar.NewWriter(gz)
	if err := tw.WriteHeader(&tar.Header{Typeflag: tar.TypeXGlobalHeader, Name: "pax_global_header",
		PAXRecords: map[string]string{"comment": id}, Format: tar.FormatPAX}); err != nil {
		return nil, err
	}
	root := &tar.Header{Typeflag: tar.TypeDir, Name: prefix, Mode: 0o775, ModTime: mtime, Uname: "root", Gname: "root",
		Format: tar.FormatUSTAR}
	if err := tw.WriteHeader(root); err != nil {
		return nil, err
	}
	for _, e := range entries {
		if ignored(e.path) {
			continue
		}
		hdr := &tar.Header{Name: prefix + e.path, Mode: 0o664, ModTime: mtime, Uname: "root", Gname: "root",
			Format: tar.FormatUSTAR}
		var content []byte
		switch {
		case e.kind == "tree":
			hdr.Typeflag, hdr.Name, hdr.Mode = tar.TypeDir, hdr.Name+"/", 0o775
		case e.kind != "blob":
			continue
		default:
			content, err = gitx.Run(dir, "cat-file", "blob", e.object)
			if err != nil {
				return nil, err
			}
			switch e.mode {
			case "100755":
				hdr.Mode = 0o775
			case "120000":
				hdr.Typeflag, hdr.Linkname, hdr.Mode = tar.TypeSymlink, string(content), 0o777
				content = nil
			}
			if content != nil && attrs[e.path+"\x00export-subst"] == "set" {
				if content, err = substitute(dir, id, content); err != nil {
					return nil, err
				}
			}
			hdr.Size = int64(len(content))
		}
		if err := tw.WriteHeader(hdr); err != nil {
			return nil, err
		}
		if _, err := tw.Write(content); err != nil {
			return nil, err
		}
	}
	if err := tw.Close(); err != nil {
		return nil, err
	}
	if err := gz.Close(); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

// attributes is export-ignore and export-subst for every path, as the tag's .gitattributes set them, keyed by path
// NUL attribute.
func attributes(dir, commit string, paths []string) (map[string]string, error) {
	cmd := exec.Command("git", "check-attr", "--source="+commit, "-z", "--stdin", "export-ignore", "export-subst")
	cmd.Dir = dir
	cmd.Stdin = strings.NewReader(strings.Join(paths, "\x00") + "\x00")
	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("git check-attr: %v", err)
	}
	fields := strings.Split(string(out), "\x00")
	attrs := map[string]string{}
	for i := 0; i+2 < len(fields); i += 3 {
		attrs[fields[i]+"\x00"+fields[i+1]] = fields[i+2]
	}
	return attrs, nil
}

var placeholder = regexp.MustCompile(`\$Format:([^$]*)\$`)

// substitute fills in each $Format:...$ placeholder with git log's expansion of it for the commit.
func substitute(dir, commit string, content []byte) ([]byte, error) {
	var failed error
	out := placeholder.ReplaceAllFunc(content, func(m []byte) []byte {
		format := string(placeholder.FindSubmatch(m)[1])
		value, err := gitx.Run(dir, "log", "-1", "--format="+format, commit)
		if err != nil {
			failed = err
			return m
		}
		return bytes.TrimSuffix(value, []byte("\n"))
	})
	return out, failed
}
