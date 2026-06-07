# Applicator Flow

This shows how findings move through application and verification.

```mermaid
flowchart TD
    A[parent_review / source findings] --> B[Applicator review]
    B --> C[3-voter legitimacy gate]
    C --> D[Evidence challenge]
    D --> E{Disposition}
    E -->|applied| F[application_result]
    E -->|declined| F
    E -->|deferred| F
    E -->|already_addressed| F
    F --> G[mpcr applicator finalize]
    G --> H[Applicator status = verifying]
    H --> I[verification_result]
    I --> J{Failed items?}
    J -->|no| K[Applicator status = completed]
    J -->|yes| L[Applicator status = blocked]
```

```mermaid
flowchart LR
    A[Finding] --> B[Anchor valid?]
    B -->|no| X[decline: invalid_anchor]
    B -->|yes| C[Scenario reproducible?]
    C -->|no| Y[decline: non_reproducible]
    C -->|yes| D[Severity proportional?]
    D -->|no| Z[decline: severity_not_supported]
    D -->|yes| E[Hallucination absent?]
    E -->|no| H[decline: hallucinated]
    E -->|yes| F[Duplicate?]
    F -->|yes| I[duplicate reason code]
    F -->|no| G[apply or defer]
```
