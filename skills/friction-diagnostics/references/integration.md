# Integration patterns

## Paste-ready `AGENTS.md` snippet

```markdown
## Friction diagnostics
WHEN any error, failure, unexpected outcome, or friction of any kind occurs THEN you SHALL immediately log it using the `friction-diagnostics` skill.
WHEN the same issue repeats without materially new evidence THEN you SHALL NOT create a duplicate entry.
WHEN friction is logged THEN you SHALL use the canonical repo-scoped `events.jsonl` target unless an explicit `--events-file` path is required.
WHEN the friction can be localized to a specific file, document, or URL THEN you SHALL populate the `sources` array in the event.
```

## Filing workflow

Filing is a single command. Use direct flags for simple payloads; `--from-json -` for shell-sensitive or multiline text.

```sh
sh scripts/report-friction.sh \
  --title "Referenced CI check script does not exist" \
  --source-type file \
  --source-ref "AGENTS.md" \
  --source-line 18 \
  --source-excerpt "Run scripts/ci-check.sh to see the current build status." \
  --expected-outcome "The scripts/ directory would contain ci-check.sh as an executable helper." \
  --actual-outcome "rg --files scripts returned no match for ci-check.sh. The file is absent." \
  --reading "The instruction at line 18 uses a concrete path in imperative form: 'Run scripts/ci-check.sh'. No conditional qualifier or note about generating the script first. Imperative instructions with literal paths refer to existing artifacts, so I treated it as a pre-existing helper. I searched with rg and found nothing. Its absence means the documentation references a file that does not exist." \
  --hindsight "I could have run ls scripts/ or rg -l ci-check before assuming the script existed." \
  --impact blocked \
  --tags "missing-script,ci-check" \
  --aliases "instructions,missing"
```

Post-hoc tag/alias additions remain available:

```sh
sh scripts/report-friction.sh --add-tags evt-NNNN "new-tag1,new-tag2"
sh scripts/report-friction.sh --add-aliases evt-NNNN "broader-group"
```

## Structured-input path

`--from-json -` is the recommended path for complex payloads:

```sh
cat <<'EOF' | sh scripts/report-friction.sh --from-json -
{
  "title": "Referenced CI check script does not exist",
  "expected_outcome": "The scripts/ directory would contain ci-check.sh.",
  "actual_outcome": "rg --files scripts returned no match for ci-check.sh.",
  "reading": "The instruction at line 18 uses a concrete path in imperative form...",
  "hindsight": "I could have verified the file exists before running it.",
  "impact": "blocked",
  "tags": ["missing-script", "ci-check"],
  "aliases": ["instructions", "missing"],
  "sources": [
    {"type": "file", "ref": "AGENTS.md", "line": 18, "excerpt": "Run scripts/ci-check.sh to see the current build status."}
  ]
}
EOF
```

## Canonical target resolution

1. Inside a git repo: `<repo>/.local/reports/friction/events.jsonl`
2. If `.local` absent but `.local*` exists: use that existing local area
3. No `.local*` in the repo: create `.local/reports/friction/events.jsonl`
4. Outside git: `<system-temp>/agent-friction/<cwd-hash>/events.jsonl`
5. Explicit override: `--events-file <path>`

## Index behavior

`INDEX.md` is auto-maintained next to `events.jsonl`. Agents do not create or rebuild it.

## Querying

```sh
sh scripts/query-friction.sh --impact blocked --format md
sh scripts/query-friction.sh --tag auth --date-from 2026-03-01
sh scripts/query-friction.sh --alias environment --source-ref "SKILL.md"
sh scripts/generate-report.sh --scan-dirs ~/repos --report-type cross-repo
```

Tag queries use substring matching: `--tag auth` matches `ssh-auth-sock`, `auth-failure`, etc. Use `--tag-exact` for exact matches.
