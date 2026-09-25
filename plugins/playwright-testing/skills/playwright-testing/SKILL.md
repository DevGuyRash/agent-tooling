---
name: playwright-testing
description: Design, run, review, and diagnose Playwright browser tests, including durable assertions, authentication fixtures, headless or isolated headed execution, and useful failure evidence.
compatibility: Requires the complete Playwright Testing plugin and Node.js with a compatible Playwright installation and browser binaries. Shared helpers target Node.js 20+ and Playwright 1.63.0. Isolated headed execution needs an optional platform display or session provider.
---

# Playwright Testing

You SHALL deliver browser tests, diagnoses, or reviews that answer the user's actual question, with claims supported by the behavior observed. Your work includes execution and test design. You SHOULD choose the useful scope from the application, requested outcome, existing coverage, configuration, and available environment.

You SHOULD use the least costly test boundary that establishes the property at issue. Rendering, browser storage, focus, navigation, permissions, and browser-mediated integrations can justify real browser tests. A mocked provider or backend changes the claim even when the UI runs in a real browser. When durability or an external effect is part of the promise, you SHALL re-observe the committed result through an independent read, fresh navigation, reload, or another appropriate surface.

## Execute and diagnose

You SHOULD use native headless execution by default and isolated headed execution when a browser or feature needs a display, or the assignment calls for it. The shared [execution interface](../../references/execution.md) can run existing commands or return ordinary Playwright objects for an authored script. [Platform isolation](../../references/isolation.md) describes setup, capabilities, resource ownership, and native qualification. You SHALL preserve relevant project settings and use the task's compatible Playwright installation.

You SHOULD choose browser, viewport, device emulation, and context settings to represent the question. A device preset changes emulation settings; the rendering OS and engine remain material evidence. For authentication or persistent browser data, use the actual storage boundary described in [authentication and storage](../../references/authentication.md).

When an execution fails, you SHOULD inspect its evidence and the application state before choosing a correction or another run. An unfamiliar page can reflect changed navigation, authentication, loading, unavailable services, or a locator assumption. Preserve the observation that distinguishes those possibilities. Stop verification when the affected checks support the task's completion; broaden it when a change or unresolved concern warrants it.

## Make tests informative

You SHOULD assert the user or product outcome and wait for its observable condition with bounded, retrying assertions. Match locators to what identifies the intended control: accessible role/name, label, an intentional stable test hook, or a scoped domain helper. You SHOULD keep repeated controls and ambiguous matches distinguishable, and centralize selectors when that reduces maintenance on a shared or externally controlled surface.

You SHOULD choose fixtures that make the relevant starting state reproducible. Fresh Playwright Test contexts isolate browser state; reused contexts, profiles, backend accounts, and external systems require their own ownership or coordination. Arrange through an API when it helps isolate the behavior under test, and preserve the real seams needed for the claimed result.

[Examples](../../references/e2e-patterns.md) cover durable outcomes, observable waits, and failure artifacts. A selector contract check can be useful where the selector itself is the maintained interface. Layout, wording, timing, and order deserve assertions when they are part of the actual product requirement.

You SHALL preserve enough failure context for a useful diagnosis and keep credentials and unrelated private material out of shared evidence. Traces and saved browser state can contain sensitive session data. For exploratory captures or a navigable evidence collection, use [Browser Survey](../browser-survey/SKILL.md) and its shared capture helpers as useful.

You SHALL report what changed or was found, what actually ran, the supported result, and consequential remaining limits. An authored test, an expected error, and a completed product journey establish different things.
