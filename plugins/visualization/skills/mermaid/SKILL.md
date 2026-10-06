---
name: mermaid
description: Write, revise, explain or troubleshoot Mermaid diagram source when Mermaid is requested or chosen, fitted to the renderer and reader that will receive it.
compatibility: Mermaid source needs no runtime to author. Rendering depends on the receiving environment's Mermaid version and enabled diagram and layout support; no renderer is bundled or installed. The diagram reference ships in this skill's directory, and the adjacent Visual Authoring skill is in the same plugin.
---

# Mermaid

You SHALL produce or revise Mermaid source that faithfully serves the assignment and the reader who will see it rendered. Mermaid is one way to make something visible; this skill covers working well within it once it is requested or chosen. While the form is still open, the adjacent [Visual Authoring](../visual-authoring/SKILL.md) skill covers exploring and choosing among directions.

Let the relationships and questions that matter choose among the diagram types the receiving renderer supports, and consider more than one arrangement: the same content reads differently as different types, as one diagram or several small ones, at different levels of detail, and with grouping, direction, labels and styling doing more or less of the work. The [Mermaid diagram reference](references/mermaid-diagrams.md) maps the documented types with sourced descriptions and syntax links; it shows what exists, not what to pick. When the content strains against every type Mermaid offers, reconsider the medium rather than bend the content.

A Mermaid code block or source file is usually enough; preserve any explicitly requested artifact or integration interface. A simple diagram needs no surrounding application, build pipeline or network access. Discover actual renderer support when compatibility affects delivery, using the receiving environment's compatibility information or [the official syntax reference](https://mermaid.js.org/intro/); support in one renderer or on the current documentation site does not establish support in another, and documentation examples may target a newer version or an optional layout engine. An unsupported feature can warrant an equivalent representation or a stated limitation while the original source is kept. Leave the renderer as the environment provides it unless the person authorizes a change.

You SHOULD retain relevant identity, direction, cardinality, units, qualifications and source relationships. An arrow can mean order, dependency, influence or a hypothesis; make the intended meaning recoverable, and keep observed paths distinguishable from expected or proposed ones where losing that status changes interpretation. Let geometry claim no causation or certainty the sources lack. Preserve important source wording and legitimate distinctions when revising layout or syntax, and treat untrusted labels as data for the selected syntax. A duplicated display label need not denote the same object; stable identifiers help when relationships or annotations depend on identity. Choose detail for the reader without hiding a consequential exception or forcing one view to express everything.

You SHALL verify the properties on which the delivery claim depends. A parser result does not establish readable typography or faithful meaning, and a successful render can omit or obscure content. Inspect the actual rendering when that property matters and a permitted environment is available; otherwise report the errors and limitations without claiming the property passed.

A diagram can be working material, an explanation or a handoff, and a recipient may correct or replace it or find something it omitted. When it will be annotated or handed on, keep its sources and the revision it shows reachable.
