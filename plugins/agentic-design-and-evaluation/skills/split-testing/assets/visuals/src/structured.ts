import { ConditionalInput, HeatmapInput, MatrixInput, TableInput } from "./model";
import { annotation, card, cell, dataTable, escapeText as e, finite, labelMarkup, named, namedLabels, numericText, scale, status, table } from "./core";

export function annotatedTable(input: TableInput): string {
  if (!input.columns.length) throw new TypeError("A table needs at least one column.");
  for (const row of input.rows) if (row.length !== input.columns.length) throw new TypeError("Every table row must match the column count.");
  return card(input, table(input.title, input.columns, input.rows.map(row => row.map(cell))), "comparison");
}

export function comparisonMatrix(input: MatrixInput): string {
  const alternatives = named(input.alternatives, "Alternatives"), dimensions = named(input.dimensions, "Dimensions");
  const alternativeLabels = namedLabels(input.alternatives), dimensionLabels = namedLabels(input.dimensions);
  const findings = new Map<string, Map<string, typeof input.findings[number]>>();
  for (const finding of input.findings) {
    if (!alternatives.has(finding.alternative) || !dimensions.has(finding.dimension)) throw new TypeError("A matrix finding refers to an undeclared alternative or dimension.");
    const row = findings.get(finding.alternative) || new Map();
    if (row.has(finding.dimension)) throw new TypeError("A matrix cell has duplicate findings; retain the distinctions in an annotated table or combine them explicitly upstream.");
    row.set(finding.dimension, finding); findings.set(finding.alternative, row);
  }
  const rows = input.alternatives.map(a => [labelMarkup(alternativeLabels.get(a.id)!) + annotation(a), ...input.dimensions.map(d => {
    const finding = findings.get(a.id)?.get(d.id);
    return finding ? cell(finding) : '<span class="av-missing">Not supplied</span>';
  })]);
  const dimensionsNotes = input.dimensions.filter(d => d.note || d.evidence?.length);
  return card(input, table(input.title, ["Alternative", ...input.dimensions.map(d => dimensionLabels.get(d.id)!)], rows) + (dimensionsNotes.length ? `<div class="av-dimension-notes"><h3>Dimension context</h3>${dimensionsNotes.map(d => `<h4>${labelMarkup(dimensionLabels.get(d.id)!)}</h4>${annotation(d)}`).join("")}</div>` : ""), "comparison");
}

/** Categorical coverage and constraint status retain the matrix's original words. */
export function coverageMatrix(input: MatrixInput): string { return comparisonMatrix(input); }
export function constraintSatisfaction(input: MatrixInput): string { return comparisonMatrix(input); }

export function conditionalRecommendations(input: ConditionalInput): string {
  const conditions = input.items.map(item => `<article class="av-recommendation"><header><h3>${e(item.condition)}</h3>${status(item.status)}</header><p class="av-implication">${e(item.implication)}</p>${annotation(item)}</article>`).join("");
  return card(input, `<div class="av-recommendations">${conditions || '<p class="av-empty">No conditions supplied.</p>'}</div>` + dataTable(input.title, ["Condition", "Implication", "Status and context"], input.items.map(item => [e(item.condition), e(item.implication), status(item.status) + annotation(item)])), "conditions");
}

export function heatmap(input: HeatmapInput): string {
  const rows = named(input.rows, "Rows"), columns = named(input.columns, "Columns");
  const rowLabels = namedLabels(input.rows), columnLabels = namedLabels(input.columns);
  const values: number[] = [], cells = new Map<string, Map<string, typeof input.cells[number]>>();
  for (const value of input.cells) {
    if (!rows.has(value.row) || !columns.has(value.column)) throw new TypeError("A heatmap cell refers to an undeclared row or column.");
    const row = cells.get(value.row) || new Map();
    if (row.has(value.column)) throw new TypeError("A heatmap cell has duplicate observations.");
    row.set(value.column, value); cells.set(value.row, row);
    const n = finite(value.value, "Heatmap value"); if (n !== null) values.push(n);
  }
  const domain = scale(values, 0, 1);
  const body = input.rows.map(row => [labelMarkup(rowLabels.get(row.id)!) + annotation(row), ...input.columns.map(column => {
    const datum = cells.get(row.id)?.get(column.id);
    if (!datum) return '<span class="av-missing">Not supplied</span>';
    const n = finite(datum.value, "Heatmap value");
    // Color carries magnitude only. Text remains opaque and zero is a real value.
    const amount = n === null || !domain ? 0 : domain.map(n) * 100;
    return `<div class="av-heat-cell" data-av-magnitude="${amount}" style="background-color:color-mix(in srgb, var(--av-heat-high) ${amount}%, var(--av-heat-low))">${numericText(n)}${input.unit ? ` ${e(input.unit)}` : ""}${status(datum.status)}${annotation(datum)}</div>`;
  })]);
  const legend = domain ? `<p class="av-muted">Color scale: ${numericText(domain.min)} to ${numericText(domain.max)}${input.unit ? ` ${e(input.unit)}` : ""}; darker means a larger supplied value. Color does not indicate preference. Missing values have no magnitude.</p>` : '<p class="av-muted">No numeric values supplied.</p>';
  const context = input.columns.filter(c => c.note || c.evidence?.length).map(c => `<h3>${labelMarkup(columnLabels.get(c.id)!)}</h3>${annotation(c)}`).join("");
  return card(input, legend + table(input.title, ["Observation", ...input.columns.map(c => columnLabels.get(c.id)!)], body) + context, "quantitative");
}
