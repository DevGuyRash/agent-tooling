# Scoped compatibility evidence

This record retains a compatibility observation removed from general runtime guidance. It identifies the evidence horizon rather than claiming that a later host implements the same contract.

## Codex raw defaultPrompt ingestion

The prior host reference recorded a check on 2026-08-17 against Codex [revision c6058cc](https://github.com/openai/codex/blob/c6058ccaa91ab17159cf805bf4d6d4edd87fe5fc/codex-rs/core-plugins/src/manifest.rs#L482-L536). At that cited raw-parser boundary, `interface.defaultPrompt` accepted either a string or a list. The surrounding normalized representation and array-shaped examples did not establish rejection of the string input.

The record accompanied reports that audits confused normalized representation with raw ingestion. That history does not establish a current failure rate, isolate a model cause, or make this old revision the current host authority. The maintained runtime lesson is to distinguish the consumer's accepted input, normalized data, examples, and submission requirements. Recheck the actual intended consumer when its revision, release channel, schema, or ingestion behavior changes.

Converter and host tests for accepted input forms supply bounded regression evidence; they do not certify a different publication channel or replace a current native-consumer check.
