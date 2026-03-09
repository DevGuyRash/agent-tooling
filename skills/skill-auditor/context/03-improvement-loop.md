# Improvement Loop

```mermaid
sequenceDiagram
    actor User
    participant Agent
    participant Target as Target Skill
    participant Router as skill-auditor SKILL.md
    participant Ref as One Reference Module
    participant Helpers as Optional Deterministic Helpers

    User->>Agent: Review or improve this skill
    Agent->>Target: Read target SKILL.md
    Agent->>Router: Route on primary question
    Router->>Ref: Load one direct reference
    Ref-->>Agent: Question-specific guidance

    opt Structural evidence adds leverage
        Agent->>Helpers: Run helper script
        Helpers-->>Agent: Deterministic evidence
    end

    Agent->>Agent: Synthesize observed evidence
    Agent->>Agent: Draft Improvement Brief
    Agent->>Target: Apply or propose changes
    Agent->>Target: Re-run prompt / task / structure checks
    Agent-->>User: Updated brief and verification result
```
