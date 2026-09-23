import { ArtifactInput, DisagreementInput, EffortInput, ExcerptInput, ExtensionInput, FailureInput, LineageInput, ScenarioInput, UncertaintyInput } from "./model";
import { annotation, card, dataTable, escapeText as e, explorerControls, finite, identifier, named, numericText, objectDetail, occurrenceLabels, status, svg, table } from "./core";
import { annotatedTable } from "./structured";
import { scatterPlot } from "./quantitative";
import { occurrenceIds } from "./categories";
import { layoutGraph } from "./graph-layout";
import { layoutRecipe, textMarkup } from "./chart-rendering";

export function evidenceExcerpts(input: ExcerptInput): string {
  return card(input, input.items.length ? `<div class="av-excerpts">${input.items.map(item => `<article class="av-excerpt"><header><h3>${e(item.label)}</h3>${status(item.status)}</header>${item.context ? `<p class="av-muted">${e(item.context)}</p>` : ""}<blockquote>${e(item.text)}</blockquote><div class="av-object-meta">${annotation(item)}</div></article>`).join("")}</div>` : '<p class="av-empty">No excerpts supplied.</p>', "interpretation");
}

export function disagreementMap(input: DisagreementInput): string {
  return card(input, `<div class="av-explorer av-positions" data-av-explorer>${explorerControls("Inspect a disputed topic", input.topics.map((topic, i) => ({ key: `topic-${i}`, label: topic.topic })))}<div class="av-object-list">${input.topics.length ? input.topics.map((topic, i) => objectDetail(`topic-${i}`, topic.topic, `${annotation(topic)}${table(topic.topic, ["Contributor", "Position", "Status and grounds"], topic.positions.map(position => [e(position.contributor), e(position.position), status(position.status) + annotation(position)]))}<p class="av-disposition"><strong>Supplied disposition:</strong> ${topic.disposition === undefined ? "Unresolved / not supplied" : e(topic.disposition)}</p>`, i === 0, "av-topic")).join("") : '<p class="av-empty">No positions supplied.</p>'}</div></div>`, "interpretation");
}

export function uncertaintyPanel(input: UncertaintyInput): string {
  return card(input, `<div class="av-observatory av-explorer" data-av-explorer>${explorerControls("Inspect an uncertainty", input.items.map((item, i) => ({ key: `uncertainty-${i}`, label: item.label })))}<div class="av-object-list">${input.items.map((item, i) => objectDetail(`uncertainty-${i}`, item.label, `${status(item.status)}<p>${e(item.reason)}</p>${annotation(item)}`, true, "av-unknown-object")).join("")}</div></div>${dataTable(input.title, ["Issue", "Reason / consequence", "Status and context"], input.items.map(item => [e(item.label), e(item.reason), status(item.status) + annotation(item)]))}`, "uncertainty");
}

export function evidenceLineage(input: LineageInput): string {
  if (input.fit !== undefined && input.fit !== 'natural' && input.fit !== 'width') throw new TypeError('Graph fit must be natural or width.');
  const nodes = named(input.nodes, "Lineage nodes"), edgeIds = occurrenceIds(input.edges, "Relation");
  for (const edge of input.edges) if (!nodes.has(edge.from) || !nodes.has(edge.to)) throw new TypeError("A lineage edge refers to an undeclared node.");
  const layout = layoutGraph(input.nodes, input.edges.map((edge, i) => ({ ...edge, id: edgeIds[i] })), { width: input.context?.width, measure: input.context?.measureText });
  const relationships = layout.edges.map(edge => {
    const path = edge.points.map((point, i) => `${i ? "L" : "M"} ${point.x} ${point.y}`).join(" ");
    const arrow = edge.arrow.map(point => `${point.x},${point.y}`).join(" "), box = edge.box;
    const supplied = input.edges[edge.index];
    return `<g class="av-graph-edge" data-av-inspect="edge-${edge.index}" data-av-edge-id="${e(edge.id)}" data-av-from="node-${edge.source}" data-av-to="node-${edge.target}" aria-label="Inspect relationship ${e(edge.id)}: ${e(supplied.from)} to ${e(supplied.to)} — ${e(supplied.relation)}"><path class="av-edge-hit" d="${path}" style="fill:none;stroke:transparent;stroke-width:18" pointer-events="stroke"/><path class="av-edge-route" d="${path}" fill="none" stroke="var(--av-axis, #738d8c)" stroke-width="1.5"/><polygon points="${arrow}" fill="var(--av-axis, #738d8c)"/><rect class="av-graph-relation-box" x="${box.x}" y="${box.y}" width="${box.width}" height="${box.height}" rx="8" fill="var(--av-sheet, #ffffff)" stroke="var(--av-line-strong, #8fa8a4)"/>${textMarkup(edge.label, box.x + 12, box.y + 12, "start", "av-graph-relation-text")}${textMarkup(edge.identity, box.x + 12, box.y + 16 + edge.label.height, "start", "av-muted av-graph-identity")}<title>${e(edge.id)}: ${e(supplied.from)} (${e(nodes.get(supplied.from)!.label)}) → ${e(supplied.to)} (${e(nodes.get(supplied.to)!.label)}): ${e(supplied.relation)}</title></g>`;
  }).join("");
  const boxes = layout.nodes.map(node => `<g class="av-graph-node" data-av-inspect="node-${node.index}" data-av-node-id="${e(node.id)}" aria-label="Inspect ${e(node.id)}: ${e(input.nodes[node.index].label)}"><rect x="${node.x}" y="${node.y}" width="${node.width}" height="${node.height}" rx="10" fill="var(--av-subtle, #f1f7f5)" stroke="var(--av-line-strong, #8fa8a4)"/>${textMarkup(node.label, node.x + 16, node.y + 16, "start", "av-graph-node-label")}${textMarkup(node.identity, node.x + 16, node.y + 24 + node.label.height, "start", "av-muted av-graph-identity")}${textMarkup(node.kind, node.x + 16, node.y + 24 + node.label.height + node.identity.height, "start", "av-muted av-graph-kind")}<title>${e(node.id)}: ${e(input.nodes[node.index].label)} (${e(input.nodes[node.index].kind)})</title></g>`).join("");
  const plot = input.nodes.length ? svg(input.title, layout.height, relationships + boxes, layout.width, input.fit ?? 'natural') : '<p class="av-empty">No evidence nodes supplied.</p>';
  const edgeIdentity = (i: number) => identifier(edgeIds[i]) + (input.edges[i].id === undefined ? ' <span class="av-muted">(occurrence)</span>' : "");
  const incident = new Map<string, number[]>();
  const nodePositions = new Map(input.nodes.map((node, i) => [node.id, i]));
  const endpointActions = (from: string, to: string): string => `<div class="av-button-group av-relation-actions" data-av-controls data-av-review-ui hidden><button type="button" class="av-button av-button-quiet" data-av-inspect="node-${nodePositions.get(from)}">Read origin</button>${from === to ? '' : `<button type="button" class="av-button av-button-quiet" data-av-inspect="node-${nodePositions.get(to)}">Read destination</button>`}</div>`;
  input.edges.forEach((edge, i) => {
    for (const id of new Set([edge.from, edge.to])) { const indices = incident.get(id) || []; indices.push(i); incident.set(id, indices); }
  });
  const related = (id: string): string => {
    const indices = incident.get(id) || [];
    if (!indices.length) return '<p class="av-note">No relationships were supplied for this item.</p>';
    return `<section class="av-related-evidence"><h4>Relationships</h4><ul>${indices.map(i => {
      const edge = input.edges[i];
      return `<li class="av-relation-record"><p class="av-relation-id">${edgeIdentity(i)}</p><div class="av-relation-ends"><span>${e(nodes.get(edge.from)!.label)}${identifier(edge.from)}</span><span aria-label="to">→</span><span>${e(nodes.get(edge.to)!.label)}${identifier(edge.to)}</span></div><p class="av-relation-wording">${e(edge.relation)}</p>${annotation(edge)}<span data-av-controls data-av-review-ui hidden><button type="button" class="av-button av-button-quiet" data-av-inspect="edge-${i}">Read relationship</button></span></li>`;
    }).join('')}</ul></section>`;
  };
  const inspector = `<details class="av-inspector" open><summary>Inspect evidence</summary><div class="av-object-list">${input.nodes.map((node, i) => objectDetail(`node-${i}`, `Node: ${node.label} · ${node.id}`, `<dl class="av-facts"><div><dt>Item ID</dt><dd>${identifier(node.id)}</dd></div><div><dt>Type</dt><dd>${e(node.kind)}</dd></div></dl>${node.detail === undefined ? "" : `<p>${e(node.detail)}</p>`}${annotation(node)}${related(node.id)}`, i === 0)).join("")}${input.edges.map((edge, i) => objectDetail(`edge-${i}`, `Relationship: ${edge.relation} · ${edgeIds[i]}`, `<dl class="av-facts"><div><dt>Relationship ID / occurrence</dt><dd>${edgeIdentity(i)}</dd></div><div><dt>From</dt><dd>${identifier(edge.from)} — ${e(nodes.get(edge.from)!.label)}</dd></div><div><dt>To</dt><dd>${identifier(edge.to)} — ${e(nodes.get(edge.to)!.label)}</dd></div></dl><p class="av-relation-wording">${e(edge.relation)}</p>${annotation(edge)}${endpointActions(edge.from, edge.to)}`)).join("")}</div></details>`;
  const choices = [...input.nodes.map((node, i) => ({ key: `node-${i}`, label: `Node: ${node.label} · ${node.id}` })), ...input.edges.map((edge, i) => ({ key: `edge-${i}`, label: `Relationship: ${edge.relation} · ${edgeIds[i]}` }))];
  return layoutRecipe(card(input, `<div class="av-constellation" data-av-explorer>${explorerControls("Inspect a node or relationship", choices)}<div class="av-explorer">${plot}${inspector}</div></div>` + '<p class="av-muted">Nodes follow supplied order, and boxes fit their text. Select a node or relationship to inspect its full wording and evidence.</p>' + dataTable("Evidence and version nodes", ["Node ID", "Label", "Kind", "Detail", "Evidence and context"], input.nodes.map(node => [identifier(node.id), e(node.label), e(node.kind), e(node.detail ?? "Not supplied"), annotation(node)])) + dataTable("Evidence and version relationships", ["Relationship ID / occurrence", "From ID", "From label", "Relation", "To ID", "To label", "Evidence and context"], input.edges.map((edge, i) => [edgeIdentity(i), identifier(edge.from), e(nodes.get(edge.from)!.label), e(edge.relation), identifier(edge.to), e(nodes.get(edge.to)!.label), annotation(edge)])), "provenance"), "lineage", input);
}

export function failureTaxonomy(input: FailureInput): string {
  return card(input, `<div class="av-explorer av-failures" data-av-explorer>${explorerControls("Issue", input.categories.map((category, i) => ({ key: `failure-${i}`, label: category.label })))}<div class="av-object-list">${input.categories.length ? input.categories.map((category, i) => objectDetail(`failure-${i}`, category.label, `<p>${e(category.definition)}</p><dl class="av-facts">${[["Alternative", category.alternative], ["Supplied frequency and denominator", category.frequency], ["Impact", category.impact], ["Conditions", category.conditions]].map(([label, value]) => `<div><dt>${e(label!)}</dt><dd>${value === undefined ? "Not supplied" : e(value)}</dd></div>`).join("")}</dl>${annotation(category)}${table(category.label, ["Case", "Observed outcome", "Evidence and context"], category.cases.map(c => [e(c.label), e(c.outcome), annotation(c)]))}`, true, "av-topic")).join("") : '<p class="av-empty">No failure categories supplied.</p>'}</div></div>`, "conditions");
}

/** Native disclosures select precomputed, explicitly named cases; no values are interpolated. */
export function scenarioExplorer(input: ScenarioInput): string {
  const labels = occurrenceLabels(input.scenarios, "Scenario");
  return card(input, `<div class="av-workbench" data-av-explorer>${explorerControls("Explore a supplied scenario", input.scenarios.map((scenario, i) => ({ key: `scenario-${i}`, label: labels[i] })))}<p class="av-muted">Choose a supplied scenario to inspect its conditions and recorded outcomes.</p><div class="av-scenario-grid">${input.scenarios.length ? input.scenarios.map((scenario, i) => objectDetail(`scenario-${i}`, labels[i], `<div class="av-scenario-condition"><p class="av-kicker">When this holds</p><p>${e(scenario.condition)}</p></div>${annotation(scenario)}${table(scenario.label, ["Alternative", "Supplied outcome", "Status and evidence"], scenario.outcomes.map(outcome => [e(outcome.alternative), e(outcome.outcome), status(outcome.status) + annotation(outcome)]))}${scenario.tradeoff ? scatterPlot(scenario.tradeoff) : ""}`, i === 0, "av-scenario")).join("") : '<p class="av-empty">No scenarios supplied.</p>'}</div></div>`, "conditions");
}

export function nativeArtifactViewer(input: ArtifactInput): string {
  const labels = occurrenceLabels(input.artifacts, "Record");
  const artifacts = input.artifacts.map((artifact, i) => {
    if (artifact.text === undefined && artifact.imageData === undefined) throw new TypeError("An artifact needs text or an embedded raster image.");
    if (artifact.imageData !== undefined) {
      if (!/^data:image\/(png|jpeg|gif|webp);base64,[A-Za-z0-9+/]+={0,2}$/.test(artifact.imageData)) throw new TypeError("Artifact images must be embedded base64 PNG, JPEG, GIF, or WebP; SVG and remote image URLs are not accepted.");
      if (!artifact.alt?.trim()) throw new TypeError("An artifact image needs meaningful alternative text.");
    }
    return objectDetail(`artifact-${i}`, labels[i], `<p class="av-artifact-type">${e(artifact.mediaType)}</p>${artifact.text !== undefined ? `<pre tabindex="0" aria-label="${e(labels[i])} text">${e(artifact.text)}</pre>` : ""}${artifact.imageData !== undefined ? `<figure class="av-visual-figure" data-av-figure data-av-figure-title="${e(labels[i])}"><img src="${e(artifact.imageData)}" alt="${e(artifact.alt!)}"/><figcaption>${e(artifact.alt!)}</figcaption></figure>` : ""}<div class="av-object-meta">${annotation(artifact)}</div>`, i === 0, "av-artifact");
  }).join("");
  const comparison = input.artifacts.length > 1 ? `<fieldset class="av-artifact-controls av-enhance-only" data-av-controls hidden><legend>Compare records</legend>${input.artifacts.map((artifact, i) => `<label class="av-compare-choice"><input type="checkbox" data-av-compare="artifact-${i}"/> ${e(labels[i])}</label>`).join("")}<p class="av-control-hint">Select records to read alongside one another.</p></fieldset>` : "";
  return card(input, `<div class="av-deck" data-av-explorer>${explorerControls("Record", input.artifacts.map((artifact, i) => ({ key: `artifact-${i}`, label: labels[i] })))}${comparison}<div class="av-deck-grid">${artifacts || '<p class="av-empty">No artifacts supplied.</p>'}</div></div>`, "artifacts");
}

export function effortTable(input: EffortInput): string {
  for (const item of input.items) finite(item.value, "Effort observation");
  return card(input, table(input.title, ["Observation", "Stage", "Measure", "Value", "Unit", "Measurement scope", "Context"], input.items.map(item => [e(item.label), e(item.stage), e(item.measure), numericText(item.value), e(item.unit), e(item.scope), annotation(item)])), "quantitative");
}

/** Extension input is data. Executable extensions require author-reviewed source modules. */
export function renderExtension(input: ExtensionInput): string {
  if (!input.purpose.trim()) throw new TypeError("Describe what the extension helps a reader understand.");
  const blocks = input.blocks.map(block => {
    switch (block.kind) {
      case "narrative": return `<p class="av-narrative">${e(block.text)}</p>`;
      case "table": return annotatedTable(block.input);
      case "scatter": return scatterPlot(block.input);
      case "excerpts": return evidenceExcerpts(block.input);
      default: throw new TypeError("Unknown extension block. Use narrative, table, scatter, or excerpts; executable markup is not an extension input.");
    }
  }).join("");
  return card(input, `<p>${e(input.purpose)}</p>${blocks}`);
}
