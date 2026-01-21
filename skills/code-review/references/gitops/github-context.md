# GitHub context ingestion (deterministic; low-bloat)

**Status:** Canonical baseline  
**Goal:** Ensure the review/apply work is grounded in the authoritative problem statement and acceptance criteria without inflating context.

---

## I) Applicability

This protocol applies WHEN the user provides (or requests you to use) any GitHub context, including:

- a PR URL
- an issue URL
- `owner/repo#<number>` references
- explicit “PR <number>” / “issue <number>” references

IF the user does not provide any GitHub context THEN you SHALL NOT guess. Instead, you SHALL ask whether there is an associated PR and/or issue and request a deterministic reference (see Section III).
You SHALL WAIT for that reference before using `gh` or treating any PR/issue text as authoritative; IF the user explicitly instructs you to proceed without it THEN you SHALL record the missing context as Assumed/Unknown (and proceed with reduced confidence).

---

## II) Required outcomes (WHAT/WHY)

WHEN GitHub context exists THEN you SHALL ensure the following outcomes exist (why: intent alignment and fewer false positives):

- **Intent:** a concise statement of what the change is trying to accomplish (derived from PR/issue title/body, not speculation).
- **Acceptance criteria:** an explicit list of success conditions (and any non-goals/out-of-scope) from PR/issue text.
- **Constraints:** any repo/process constraints stated in PR/issue (security, compatibility, rollout, testing, deadlines).
- **Decision log:** if PR/issue contains design tradeoffs, that rationale is captured (briefly) so the review can judge against it.

To avoid context bloat, you SHALL store only extracted obligations and rationale (bullets), not entire thread dumps.

---

## III) Deterministic input formats (no guessing)

You SHALL request/accept GitHub context in one of these formats:

1) Full URL:
   - `https://github.com/<owner>/<repo>/pull/<number>`
   - `https://github.com/<owner>/<repo>/issues/<number>`

2) Explicit typed reference:
   - `PR <owner>/<repo>#<number>`
   - `Issue <owner>/<repo>#<number>`

3) Short typed reference for the current worktree repo (ONLY when you are operating in that repo AND the repo is resolved deterministically via Section IV.1):
   - `PR <number>`
   - `Issue <number>`

IF the user provides `owner/repo#<number>` without specifying PR vs issue THEN you SHALL ask which type it is (do not guess).

IF the user provides only a bare number (e.g., `123` or `#123`) THEN you SHALL ask at least one clarifying question and wait:

- Is it a PR or an issue?

IF you cannot determine the intended repo deterministically (Section IV.1) THEN you SHALL also ask:

- Which repo (`owner/repo`)?

---

## IV) Deterministic acquisition via `gh` (read-only)

This section provides command shapes that are known-good and do not require guessing.
You SHALL use them ONLY if `gh` is available and authenticated; otherwise you SHALL use the fallback in Section V.

### 1) Resolve repo deterministically (required when repo is not explicitly provided)

From within a git working tree that is linked to GitHub:

```bash
gh repo view --json nameWithOwner --jq .nameWithOwner
```

IF `gh repo view ...` fails or returns a repo that does not match the intended target THEN you SHALL use the fallback in Section V.

IF you resolve `owner/repo` from the current worktree THEN you SHALL state the resolved value before using it, and you SHALL use it consistently for all subsequent `gh ... --repo <owner>/<repo>` commands.

### 2) Fetch minimal PR context (default)

```bash
gh pr view <number> --repo <owner>/<repo> \
  --json number,url,title,state,body,labels,baseRefName,headRefName \
  --jq '{number,url,title,state,baseRefName,headRefName,labels:[.labels[].name],body}'
```

### 3) Fetch minimal issue context (default)

```bash
gh issue view <number> --repo <owner>/<repo> \
  --json number,url,title,state,body,labels \
  --jq '{number,url,title,state,labels:[.labels[].name],body}'
```

### 4) Progressive disclosure for discussions (ONLY when needed)

IF required outcomes in Section II are not satisfied after reading title/body THEN you SHALL expand scope deterministically:

- **Top-level PR comments:** `gh pr view <number> --repo <owner>/<repo> --comments`
- **Unresolved inline review threads** (not included in `--comments`):

```bash
gh api graphql -F owner=<owner> -F repo=<repo> -F number=<pr> -f query='
  query($owner:String!, $repo:String!, $number:Int!) {
    repository(owner:$owner, name:$repo) {
      pullRequest(number:$number) {
        reviewThreads(first:100) {
          nodes { isResolved comments(first:10) { nodes { author { login } body path line } } }
        }
      }
    }
  }' --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false)'
```

For issues (ONLY when required outcomes in Section II are not satisfied after reading title/body), you SHALL expand deterministically:

- **Top-level issue comments:** `gh issue view <number> --repo <owner>/<repo> --comments`

### 5) CI status (ONLY when relevant)

IF any of the following is true THEN you SHALL check CI status deterministically:

- the user asked you to assess CI/mergeability
- applying findings / merge readiness is in scope
- the PR text/labels mention required checks
- a finding depends on CI outcomes

```bash
gh pr checks <number> --repo <owner>/<repo>
```

---

## V) Fallback when `gh` is unavailable (still deterministic)

IF you cannot use `gh` successfully THEN you SHALL ask the user to paste the minimum necessary context:

- PR/issue title and body (verbatim)
- any explicit acceptance criteria / constraints
- any critical discussion excerpts that define requirements (link + quoted excerpt)

You SHALL then proceed using that pasted content as the authoritative overlay for the review/apply work.
