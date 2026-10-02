# northgate-ticket-router

Prompt for the model that routes incoming IT tickets at Northgate Logistics, and the eval results behind prompt changes.

- `prompts/` — prompt versions. The router service loads the file named in `ROUTER_PROMPT` (currently `prompts/v4.md`). The same prompt is sent to every model in the fallback pool.
- `evals/scenarios.md` — the eval suite: 12 tickets with the expected routing.
- `results/` — eval results.
- `decisions/` — one record per prompt change, adopted or not. Start from `decisions/TEMPLATE.md`.

## Model pool

The router sends each ticket to one of four models (`sonnet`, `gpt-mini`, `flash`, `llama-70b`), chosen by load and cost; about a third of tickets go to `flash`, the cheapest. All four get the same prompt.

## How the evals run

A run sends every scenario ticket to each of the four models, 5 times per ticket per model. A reply passes when it is valid JSON with exactly the four keys and the expected queue and priority. Results files have one row per scenario, model, and prompt:

```
scenario,model,prompt,repeats,passed
```

The nightly job runs the production prompt; the Wednesday run is kept in `results/nightly/` as a weekly snapshot. A side-by-side run (`results/<date>-<new>-vs-<old>.csv`) runs two prompts in the same job, interleaved, on the same models and repeats.
