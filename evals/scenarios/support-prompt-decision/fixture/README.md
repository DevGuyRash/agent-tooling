# larkspur-support-prompt

System prompt for the Larkspur Home support assistant, and the eval results we use to decide prompt changes.

- `prompts/` — prompt versions. Production uses whatever `PRODUCTION_PROMPT` in the deploy config points at (currently `prompts/v7.md`).
- `evals/scenarios.md` — the eval suite: 12 scripted customer conversations, each with a rubric.
- `results/` — eval results.
- `decisions/` — one record per prompt change we adopted or turned down. Copy `decisions/TEMPLATE.md`.

## How the evals run

Each run plays every scenario against each of the three models we serve on (`sonnet`, `gpt-mini`, `flash`), 5 times per scenario per model. A conversation passes when the rubric grader passes it. A results file has one row per scenario, model, and prompt:

```
scenario,model,prompt,repeats,passed
```

`passed` counts how many of the `repeats` conversations passed.

The nightly job runs the production prompt against the suite every night; we keep the Wednesday run as a weekly snapshot in `results/nightly/`. A side-by-side run (`results/<date>-<new>-vs-<old>.csv`) plays both prompts in the same job, interleaved, with the same models and repeats.

Changing the production prompt needs a decision record and a change ticket.
