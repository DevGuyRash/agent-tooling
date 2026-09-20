/** Optional focused exploration alongside the complete supplied comparison. */
import { MatrixInput, UnknownsInput } from "./model";
import { annotation, card, cell, escapeText as e, explorerControls, identifier, labelMarkup, namedLabels, objectDetail, table } from "./core";
import { comparisonMatrix } from "./structured";
import { unknownsMap } from "./landscape";

export function comparisonJourney(input: MatrixInput): string {
  // The original matrix validates identities, preserves all cells and remains available.
  const complete = comparisonMatrix({ ...input, id: undefined });
  const dimensionLabels = namedLabels(input.dimensions), alternativeLabels = namedLabels(input.alternatives);
  const choices = input.alternatives.map((alternative, i) => ({ key: `alternative-${i}`, label: alternativeLabels.get(alternative.id)! }));
  const navigation = choices.length ? `<div class="av-journey-controls av-enhance-only" data-av-controls hidden><button type="button" class="av-button" data-av-step="-1">Previous alternative</button><button type="button" class="av-button" data-av-step="1">Next alternative</button></div>` : "";
  const steps = input.alternatives.map((alternative, i) => {
    const rows = input.dimensions.map(dimension => {
      const finding = input.findings.find(f => f.alternative === alternative.id && f.dimension === dimension.id);
      return [labelMarkup(dimensionLabels.get(dimension.id)!) + annotation(dimension), finding ? cell(finding) : '<span class="av-missing">Not supplied</span>'];
    });
    return objectDetail(`alternative-${i}`, alternativeLabels.get(alternative.id)!, `${typeof alternativeLabels.get(alternative.id) === "string" ? `<p class="av-object-identity">${identifier(alternative.id)}</p>` : ""}${annotation(alternative)}${table(`Requirements and findings for ${alternative.label}`, ["Dimension", "Supplied finding"], rows)}`, i === 0, "av-journey-step");
  }).join("");
  return card(input, `<div class="av-journey" data-av-explorer>${explorerControls("Option", choices)}${navigation}<div class="av-object-list">${steps || '<p class="av-empty">No alternatives supplied.</p>'}</div></div><details class="av-data" data-av-content-view="data"><summary>Complete comparison matrix</summary>${complete}</details>`, "comparison");
}

export function uncertaintyObservatory(input: UnknownsInput): string {
  const complete = unknownsMap({ ...input, id: undefined });
  const choices = input.issues.map((issue, i) => ({ key: `issue-${i}`, label: issue.label }));
  const issues = input.issues.map((issue, i) => objectDetail(`issue-${i}`, issue.label, `<div class="av-uncertainty-basis"><p class="av-kicker">Why it matters</p><p>${e(issue.relevance)}</p></div>${annotation(issue)}${table("Affected alternatives and unresolved consequences", ["Alternative ID", "Alternative", "Supplied consequence"], input.alternatives.map(alternative => {
    const affected = issue.affected.find(item => item.alternative === alternative.id);
    return [identifier(alternative.id), e(alternative.label) + annotation(alternative), affected ? e(affected.consequence) + annotation(affected) : '<span class="av-missing">No relationship supplied</span>'];
  }))}`, i === 0, "av-unknown-object")).join("");
  return card(input, `<div class="av-observatory" data-av-explorer>${explorerControls("Question", choices)}<div class="av-object-list">${issues || '<p class="av-empty">No unanswered questions supplied.</p>'}</div></div><details class="av-data" data-av-content-view="data"><summary>Complete unknowns map</summary>${complete}</details>`, "uncertainty");
}
