---
name: browser-survey
description: Explore websites and web applications, capture reproducible visual states, investigate browser behavior, and organize or compare screenshots, traces, and existing capture collections.
compatibility: Requires the complete Playwright Testing plugin and Node.js with a compatible Playwright installation and browser binaries. Shared helpers target Node.js 20+ and Playwright 1.63.0. Isolated headed execution needs an optional platform display or session provider.
---

# Browser Survey

You SHALL investigate the requested site, application, or capture collection and deliver evidence that helps the user understand, assess, or reproduce what matters. You SHOULD choose the states, interactions, representations, and depth from the assignment and what you observe. A useful survey can be a focused diagnosis, a broad exploration, a comparison, or a small set of explanatory captures.

The shared runtime supports ordinary Playwright code. Use it for repeated execution, discovery, capture, storage, and indexing work; supply the application's journey and interpretation yourself. Read the relevant [execution interface](../../references/execution.md) and [survey patterns](../../references/survey-patterns.md). The [runnable example](../../references/examples/survey.mjs) captures an initial state and records candidates for further exploration.

## Explore meaningful states

Start from the question and available application context. Inspect rendered navigation, controls, frames, scroll regions, and relevant routes. Discovery returns observations and locator clues; choose which destinations and actions contribute within the user's mandate. Additional controls may appear after opening a menu, changing a view, entering a form, or revealing content.

You SHOULD retain meaningful query parameters, fragments, settings, identities, and action history. Different states can share a URL, and repeated labels can identify different items. Select useful viewport, appearance, and browser combinations; expand coverage where the task, layout transitions, unusual content, or observed defects justify it. Use explicit work and time bounds for open-ended traversal, retaining pending work when a bound is reached.

You SHOULD use native headless execution by default and isolated headed execution when the task needs it. [Platform isolation](../../references/isolation.md) describes the available backends and lifecycle. [Authentication and storage](../../references/authentication.md) covers reproducible sessions. Device emulation and a virtual display have distinct effects; retain the actual rendering environment with the observations.

## Capture and interpret

You SHOULD establish readiness from the property being inspected. Fonts and images settling can help a visual capture; a loaded document or a quiet network does not establish that the requested application state is ready. Supply a specific readiness condition where needed and preserve timeouts or partial states as observations.

Choose viewport, element, region, scroll-sequence, trace, or short video evidence according to what makes the finding understandable. Capture the context needed to recover the original state. The evidence store retains each observation while sharing identical image bytes, supports interrupted-run recovery, and produces a searchable local gallery. Discovery, sampling limits, and captured views establish their observed coverage.

You SHALL distinguish observations from diagnoses and expected outcomes. Compare supported corresponding states and preserve ambiguous matches for inspection. When the user needs a maintained regression test, carry the relevant finding and original grounds into [Playwright Testing](../playwright-testing/SKILL.md).

You SHALL deliver the useful findings, selected evidence, reproduction context, and material gaps. Keep authentication state and unrelated private content out of shared captures, and preserve original evidence when producing derived views or comparisons.
