# Protocol Summary

1. Execute Phase 0 requirements capture before research or generation.
2. Execute Phase 1 research before architecture, task list, or emitted files.
3. Execute Phase 2 architecture planning before the task list.
4. Classify unresolved image references; block file emission in enforcing mode when unresolved remain.
5. Evaluate compose policy pack and derive deterministic report/patch artifacts (`policy-check`, `policy-plan`), then apply approved plans with `policy-apply`.
6. Validate init-sidecar conformance for all `*-init-perms` services against the canonical contract (user `0:0`, cap_drop ALL, cap_add CHOWN+FOWNER, security_opt no-new-privileges, read_only true, network_mode none, restart no, no `profiles:` key).
7. Emit configuration files only after all prior gates and critical unknown handling.
8. Run `output-check` against final markdown before final delivery.
9. If Docker daemon is available, run `verify` and include the report in delivery.
10. Include a single-line traceability marker in each major section.

Use this with `<skills-file-root>/scripts/docker-architect-compose` outputs to keep sections deterministic.
