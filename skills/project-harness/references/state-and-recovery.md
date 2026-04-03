# State, Candidates, and Recovery

The generator keeps local state under `.local/harness/`.

## State file

Path:
- `.local/harness/state.json`

The state records:
- generator version
- detection output summary
- selected architecture, CI mode, release overlay, and dist storage
- managed writes versus candidate-only outputs
- warnings and notes

Example shape:

```json
{
  "version": "2.3.0",
  "detected": {
    "languages": ["rust", "javascript"],
    "build_tools": ["cargo", "npm"],
    "frameworks": [],
    "task_runners": [],
    "ci_systems": ["github-actions"],
    "distribution_hints": {
      "has_compiled_binaries": true,
      "dist_exists": false,
      "dist_os_subdirs": false,
      "dist_ignored": false,
      "dist_lfs_tracked": false,
      "local_ignored": true
    }
  },
  "selected": {
    "architecture": "cross-os-dist",
    "ci_mode": "direct",
    "release_overlay": true,
    "dist_storage": "artifacts"
  },
  "generated": {
    "render_dir": ".local/harness/render",
    "managed_writes": ["justfile", ".github/workflows/ci.yml"],
    "candidate_only": [".github/workflows/release-cross-os.yml"]
  },
  "warnings": [],
  "notes": []
}
```

## Candidate directory

Path:
- `.local/harness/render/`

Use it when:
- an unmanaged file blocked a direct write
- you want to diff the generated version before copying it over manually
- you want the skill to show its proposal without mutating project files

## Recovery workflow

If an update result is not what you wanted:
1. inspect `.local/harness/state.json`
2. inspect `.local/harness/render/`
3. adjust `--architecture`, `--ci-mode`, `--dist-storage`, or `--release-overlay`
4. rerun `render` for preview
5. rerun `update` only when the target files should be managed or remain absent

## Validation and smoke tests

```bash
python <skills-file-root>/scripts/validate_skill.py <skills-file-root> --pretty
python <skills-file-root>/scripts/validate_skill.py <skills-file-root> --pretty --smoke
```

That checks structure, Python compilation, and a small generator smoke suite.
