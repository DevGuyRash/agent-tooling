<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **agent-skills** (9115 symbols, 17155 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/agent-skills/context` | Codebase overview, check index freshness |
| `gitnexus://repo/agent-skills/clusters` | All functional areas |
| `gitnexus://repo/agent-skills/processes` | All execution flows |
| `gitnexus://repo/agent-skills/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |
| Work in the Tests area (615 symbols) | `.claude/skills/generated/tests/SKILL.md` |
| Work in the Scripts area (141 symbols) | `.claude/skills/generated/scripts/SKILL.md` |
| Work in the Assets area (73 symbols) | `.claude/skills/generated/assets/SKILL.md` |
| Work in the Cluster_136 area (49 symbols) | `.claude/skills/generated/cluster-136/SKILL.md` |
| Work in the Cluster_114 area (37 symbols) | `.claude/skills/generated/cluster-114/SKILL.md` |
| Work in the Validate_output_contract area (36 symbols) | `.claude/skills/generated/validate-output-contract/SKILL.md` |
| Work in the Cluster_113 area (35 symbols) | `.claude/skills/generated/cluster-113/SKILL.md` |
| Work in the Cluster_143 area (22 symbols) | `.claude/skills/generated/cluster-143/SKILL.md` |
| Work in the Cluster_99 area (19 symbols) | `.claude/skills/generated/cluster-99/SKILL.md` |
| Work in the Cluster_177 area (19 symbols) | `.claude/skills/generated/cluster-177/SKILL.md` |
| Work in the Cluster_109 area (18 symbols) | `.claude/skills/generated/cluster-109/SKILL.md` |
| Work in the Cluster_165 area (18 symbols) | `.claude/skills/generated/cluster-165/SKILL.md` |
| Work in the Cluster_181 area (18 symbols) | `.claude/skills/generated/cluster-181/SKILL.md` |
| Work in the Validate_ area (18 symbols) | `.claude/skills/generated/validate/SKILL.md` |
| Work in the Cluster_139 area (17 symbols) | `.claude/skills/generated/cluster-139/SKILL.md` |
| Work in the Cluster_141 area (16 symbols) | `.claude/skills/generated/cluster-141/SKILL.md` |
| Work in the Cluster_166 area (16 symbols) | `.claude/skills/generated/cluster-166/SKILL.md` |
| Work in the Cluster_116 area (15 symbols) | `.claude/skills/generated/cluster-116/SKILL.md` |
| Work in the Cluster_88 area (13 symbols) | `.claude/skills/generated/cluster-88/SKILL.md` |
| Work in the Evaluate_dockerfile_policy area (13 symbols) | `.claude/skills/generated/evaluate-dockerfile-policy/SKILL.md` |

<!-- gitnexus:end -->
