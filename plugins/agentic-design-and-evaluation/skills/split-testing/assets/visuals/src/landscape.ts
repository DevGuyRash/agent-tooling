import { ConfidenceInput, DecisionHistoryInput, FreshnessInput, LineageInput, MatrixInput, ReliabilityInput, UnknownsInput } from "./model";
import { annotation, card, cell, dataTable, escapeText as e, explorerControls, labelMarkup, named, namedLabels, noPlot, objectDetail, scale, svg, table } from "./core";
import { evidenceLineage } from "./qualitative";
import { comparisonMatrix } from "./structured";
import { layoutRecipe, rowLabelMarkup, rowPlot, rowsLayout, sceneWidth } from "./chart-rendering";

/** Dates are ISO calendar days to avoid hidden timezone-dependent ordering. */
export function evidenceFreshness(input: FreshnessInput): string {
  const parsed = input.events.map(event => {
    if (event.date === null) return null;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(event.date)) throw new TypeError("Freshness dates must be ISO calendar days (YYYY-MM-DD) or null.");
    const date = Date.parse(`${event.date}T00:00:00Z`);
    if (!Number.isFinite(date) || new Date(date).toISOString().slice(0, 10) !== event.date) throw new TypeError("Invalid freshness calendar day.");
    return date;
  });
  const width = sceneWidth(input.context), left = width < 560 ? Math.max(110, width * .34) : 220;
  const numbers = parsed.filter((value): value is number => value !== null), domain = scale(numbers, left, width - 70), layout = rowsLayout(input.events.map(event => event.label), left - 35, input.context);
  if (domain) {
    domain.ticks = [...new Set(domain.ticks.map(value => Date.parse(new Date(value).toISOString().slice(0, 10) + "T00:00:00Z")))];
    domain.tickLabels = domain.ticks.map(value => new Date(value).toISOString().slice(0, 10)); domain.offset = null;
  }
  const plot = domain ? rowPlot(input.title, layout.height, input.events.map((event, index) => {
    const y = layout.rows[index].y, date = parsed[index];
    return date === null ? `<text x="${left + 8}" y="${y + 4}">Date missing</text>` : `<circle cx="${domain.map(date)}" cy="${y}" r="5" fill="var(--av-series-1)" data-av-inspect="event-${index}" aria-label="Inspect ${e(event.label)}"><title>${e(event.date!)} — ${e(event.event)}</title></circle>`;
  }).join(""), layout.rows.map(row => rowLabelMarkup(row, left - 15)).join(""), domain, "Calendar date (UTC)", input.context, left) : noPlot();
  const inspector = `<details class="av-inspector" open><summary>Inspect events</summary>${input.events.map((event, index) => objectDetail(`event-${index}`, event.label, `<dl class="av-facts"><div><dt>Source</dt><dd>${e(event.source)}</dd></div><div><dt>Date</dt><dd>${event.date === null ? "Missing" : e(event.date)}</dd></div><div><dt>Supplied event</dt><dd>${e(event.event)}</dd></div></dl><p>${e(event.assessment ?? "Assessment not supplied")}</p>${annotation(event)}`, index === 0)).join("")}</details>`;
  return layoutRecipe(card(input, `<div class="av-freshness" data-av-explorer>${explorerControls("Event", input.events.map((event, index) => ({ key: `event-${index}`, label: event.label })))}<div class="av-explorer">${plot}${inspector}</div></div>` + dataTable(input.title, ["Event", "Source", "Date", "Event meaning", "Supplied assessment", "Context"], input.events.map(event => [e(event.label), e(event.source), event.date === null ? "Missing" : e(event.date), e(event.event), e(event.assessment ?? "Not supplied"), annotation(event)])), "history"), "freshness", input);
}

export function unknownsMap(input: UnknownsInput): string {
  const alternatives = named(input.alternatives, "Affected alternatives");
  const alternativeLabels = namedLabels(input.alternatives);
  const rows = input.issues.map(issue => {
    const affected = new Map<string, typeof issue.affected[number]>();
    for (const item of issue.affected) {
      if (!alternatives.has(item.alternative) || affected.has(item.alternative)) throw new TypeError("Unknowns must reference unique declared alternatives within each issue.");
      affected.set(item.alternative, item);
    }
    return [e(issue.label) + annotation(issue), e(issue.relevance), ...input.alternatives.map(a => {
      const item = affected.get(a.id);
      return item ? e(item.consequence) + annotation(item) : '<span class="av-missing">No relationship supplied</span>';
    })];
  });
  const alternativesContext = input.alternatives.filter(a => a.note || a.evidence?.length).map(a => `<h3>${labelMarkup(alternativeLabels.get(a.id)!)}</h3>${annotation(a)}`).join("");
  return card(input, table(input.title, ["Unanswered question", "Supplied relevance", ...input.alternatives.map(a => alternativeLabels.get(a.id)!)], rows) + alternativesContext, "uncertainty");
}

export function confidenceProvenance(input: ConfidenceInput): string {
  return card(input, `<div class="av-confidence" data-av-explorer>${explorerControls("Inspect the grounds for a claim", input.claims.map((claim, i) => ({ key: `claim-${i}`, label: claim.claim })))}<div class="av-object-list">${input.claims.length ? input.claims.map((claim, i) => objectDetail(`claim-${i}`, claim.claim, `<p class="av-supplied-judgment"><strong>Supplied judgment:</strong> ${e(claim.judgment)}</p>${table(claim.claim, ["Basis / quality dimension", "Supplied observation", "Evidence and context"], claim.basis.map(basis => [e(basis.dimension), e(basis.observation), annotation(basis)]))}${annotation(claim)}`, true, "av-topic")).join("") : '<p class="av-empty">No confidence judgments supplied.</p>'}</div></div>`, "provenance");
}

export function reliabilityProfile(input: ReliabilityInput): string {
  // Reuse the validated matrix, with condition and behavior roles kept explicit.
  const matrix: MatrixInput = { ...input, alternatives: input.conditions, dimensions: input.behaviors, findings: input.observations.map(o => ({ ...o, alternative: o.condition, dimension: o.behavior })) };
  const rendered = comparisonMatrix(matrix);
  return rendered.replace('<th scope="col">Alternative</th>', '<th scope="col">Operating condition</th>');
}

/** Each requirement is independently expandable; the renderer never computes viability. */
export function constraintMap(input: MatrixInput): string {
  comparisonMatrix(input); // Validate declared identities and uniqueness before rendering.
  const alternativeLabels = namedLabels(input.alternatives), dimensionLabels = namedLabels(input.dimensions);
  return card(input, `<div class="av-workbench" data-av-explorer>${explorerControls("Requirement", input.dimensions.map((requirement, i) => ({ key: `requirement-${i}`, label: dimensionLabels.get(requirement.id)! })))}<div class="av-object-list">${input.dimensions.map((requirement, i) => objectDetail(`requirement-${i}`, dimensionLabels.get(requirement.id)!, `${annotation(requirement)}${table(requirement.label, ["Alternative", "Supplied constraint finding"], input.alternatives.map(a => {
    const finding = input.findings.find(f => f.alternative === a.id && f.dimension === requirement.id);
    return [labelMarkup(alternativeLabels.get(a.id)!) + annotation(a), finding ? cell(finding) : '<span class="av-missing">Not supplied</span>'];
  }))}`, true, "av-scenario")).join("")}</div></div>` + '<p class="av-muted">Collapsing a requirement only changes what is visible. It does not waive that requirement or recompute feasibility.</p>', "conditions");
}

export function decisionHistory(input: DecisionHistoryInput): string {
  return card(input, `<div class="av-decision-trail" data-av-explorer>${explorerControls("Inspect a decision in context", input.decisions.map((decision, i) => ({ key: `decision-${i}`, label: decision.label })))}<p class="av-muted">Entries retain the caller’s order and distinguish information available at the decision from later changes.</p>${input.decisions.length ? `<ol class="av-history">${input.decisions.map((decision, i) => `<li>${objectDetail(`decision-${i}`, decision.label, `<p class="av-history-time">${e(decision.when)}</p><p class="av-supplied-judgment"><strong>Decision:</strong> ${e(decision.decision)}</p><dl class="av-facts"><div><dt>Available then</dt><dd>${e(decision.availableThen)}</dd></div><div><dt>Changes since</dt><dd>${e(decision.changesSince ?? "Not supplied")}</dd></div>${decision.supersedes !== undefined ? `<div><dt>Supersedes / revises</dt><dd>${e(decision.supersedes)}</dd></div>` : ""}</dl>${annotation(decision)}`, true)}</li>`).join("")}</ol>` : '<p class="av-empty">No decisions supplied.</p>'}</div>`, "history");
}

/** The caller names argument node kinds and edge semantics; no weight is assigned. */
export function argumentMap(input: LineageInput): string { return evidenceLineage(input); }
