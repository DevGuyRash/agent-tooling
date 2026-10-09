# Option Map

An Option Map is the design-phase output. It helps a user who does not know exactly what they want see plausible directions and pick one.

## Ingredients

Use only what helps the next decision:

- Source anchors: exact wording or facts that shape the option space.
- Plausible directions: distinct product interpretations, not minor implementation variants.
- What each direction optimizes for.
- Tradeoffs, risks, and non-goals.
- Weak or rejected options when they are tempting but poor fits.
- Recommended direction with reasoning.
- Questions whose answer would change the recommendation.
- What would become durable after the user chooses.

## Quality Rules

Phrase the recommendation as a default direction the user can accept, reject, or refine, and state the uncertainty that remains.

Avoid option theater: list only directions that differ as product interpretations, and give the recommendation its own heading, as below.

## Minimal Shape

```md
## Option Map

Source signals:
- <source wording or context>

Directions:
1. <direction>: optimizes for <value>; tradeoff <cost/risk>.
2. <direction>: optimizes for <value>; tradeoff <cost/risk>.

Recommendation:
- Start with <direction> because <source-grounded reason>.

Decision needed:
- <question only if it changes the recommendation>
```

Do not write this to `context/docs/` until the user accepts or chooses a direction.
