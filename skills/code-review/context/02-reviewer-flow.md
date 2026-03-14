# Reviewer Flow

This is the route-first review path for reviewer mode.

```mermaid
flowchart TD
    A[Changed files / public interfaces /\nbehavior-facing artifacts] --> B[mpcr route]
    B --> C[surface_map]
    B --> D[route_decision]
    D --> E[Load only selected policy packs]
    E --> F[Planned workers]
    F --> G[child_findings artifacts]
    G --> H[parent_review artifact]
    H --> I[mpcr validate --layer hard]
    I --> J[mpcr reviewer finalize]
    H --> K[mpcr render --format markdown]
```

```mermaid
sequenceDiagram
    participant U as User / Agent
    participant R as Router
    participant W as Review Workers
    participant S as Synthesizer
    participant V as Validator
    participant L as Session Ledger

    U->>R: route inputs
    R-->>U: surface_map + route_decision
    U->>W: selected workers/modules only
    W-->>S: child_findings
    S-->>U: parent_review
    U->>V: hard validate parent_review
    V-->>U: pass / fail
    U->>L: finalize persisted artifact refs
```
