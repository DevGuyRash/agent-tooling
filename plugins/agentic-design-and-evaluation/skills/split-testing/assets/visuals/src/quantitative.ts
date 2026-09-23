import { DistributionInput, IntervalInput, PairedInput, ScatterInput, TrajectoryInput, NumericObservation } from "./model";
import { annotation, axisLabel, card, dataTable, escapeText as e, explorerControls, finite, identifier, labelMarkup, namedLabels, noPlot, numericText, objectDetail, scale, status, svg, xAxis, yAxis } from "./core";
import { categoryStyle, occurrenceIds, chartCategories } from "./categories";
import { axisHeight, labelLayout, layoutRecipe, marker, markerLegend, rowLabelMarkup, rowPlot, rowsLayout, sceneWidth, statusWord, textMarkup } from "./chart-rendering";

export function pairedComparison(input: PairedInput): string {
  const values: number[] = [];
  for (const pair of input.pairs) for (const item of [pair.left, pair.right]) { const value = finite(item, "Paired value"); if (value !== null) values.push(value); }
  const width = sceneWidth(input.context), left = width < 560 ? Math.max(105, width * .3) : 185;
  const axis = axisLabel(input.axis, input.unit), domain = scale(values, left, width - 55), layout = rowsLayout(input.pairs.map(pair => pair.label), left - 30, input.context);
  const plot = domain ? rowPlot(input.title, layout.height, input.pairs.map((pair, i) => {
    const y = layout.rows[i].y, first = finite(pair.left, "Left value"), second = finite(pair.right, "Right value");
    return (first !== null && second !== null ? `<line class="av-pair-link" stroke="var(--av-axis)" x1="${domain.map(first!)}" x2="${domain.map(second!)}" y1="${y}" y2="${y}"/>` : "")
      + (first === null ? "" : marker({ color: 1, shape: "circle", dash: "" }, domain.map(first), y, `${input.leftLabel}: ${pair.left}`))
      + (second === null ? "" : marker({ color: 2, shape: "square", dash: "" }, domain.map(second), y, `${input.rightLabel}: ${pair.right}`));
  }).join(""), layout.rows.map(row => rowLabelMarkup(row, left - 15)).join(""), domain, axis, input.context, left) : noPlot();
  const leftName = input.leftLabel === input.rightLabel ? `Left: ${input.leftLabel}` : input.leftLabel, rightName = input.leftLabel === input.rightLabel ? `Right: ${input.rightLabel}` : input.rightLabel;
  return layoutRecipe(card(input, `<p class="av-legend"><span style="color:var(--av-series-1)">●</span> ${e(leftName)} <span style="color:var(--av-series-2)">■</span> ${e(rightName)}</p>${plot}${dataTable(input.title, ["Pair", `${leftName}: ${axis}`, `${rightName}: ${axis}`, "Context"], input.pairs.map(pair => [e(pair.label), numericText(pair.left), numericText(pair.right), annotation(pair)]))}`, "quantitative"), "paired", input);
}

export function intervalPlot(input: IntervalInput): string {
  if (!input.intervalLabel.trim()) throw new TypeError("Supply an intervalLabel explaining what the bounds mean.");
  const values: number[] = [];
  for (const item of input.items) {
    const low = finite(item.low, "Lower bound"), high = finite(item.high, "Upper bound"), estimate = finite(item.estimate, "Estimate");
    if (low !== null && high !== null && low > high) throw new TypeError("Lower interval bounds must not exceed upper bounds.");
    for (const value of [low, high, estimate]) if (value !== null) values.push(value);
  }
  const width = sceneWidth(input.context), left = width < 560 ? Math.max(105, width * .3) : 185;
  const axis = axisLabel(input.axis, input.unit), domain = scale(values, left, width - 55), layout = rowsLayout(input.items.map(item => item.label), left - 30, input.context);
  const plot = domain ? rowPlot(input.title, layout.height, input.items.map((item, i) => {
    const y = layout.rows[i].y, low = finite(item.low, "Low"), high = finite(item.high, "High"), estimate = finite(item.estimate, "Estimate");
    const line = low !== null && high !== null ? `<line stroke="var(--av-series-1)" stroke-width="3" x1="${domain.map(low)}" x2="${domain.map(high)}" y1="${y}" y2="${y}"/>` : "";
    const caps = [low, high].map((value, j) => value === null ? "" : `<line stroke="var(--av-series-1)" stroke-width="2" x1="${domain.map(value)}" x2="${domain.map(value)}" y1="${y - 7}" y2="${y + 7}"><title>${j ? "Upper" : "Lower"} bound: ${e(value)}</title></line>`).join("");
    return line + caps + (estimate === null ? "" : marker({ color: 2, shape: "circle", dash: "" }, domain.map(estimate), y, `Supplied estimate: ${estimate}`));
  }).join(""), layout.rows.map(row => rowLabelMarkup(row, left - 15)).join(""), domain, axis, input.context, left) : noPlot();
  return layoutRecipe(card(input, `<p>${e(input.intervalLabel)}.</p>${plot}${dataTable(input.title, ["Observation", `Lower: ${axis}`, `Upper: ${axis}`, `Estimate: ${axis}`, "Context"], input.items.map(item => [e(item.label), numericText(item.low), numericText(item.high), numericText(item.estimate), annotation(item)]))}`, "quantitative"), "interval", input);
}

export function distribution(input: DistributionInput): string {
  const ids = occurrenceIds(input.groups, "Group"), groups = input.groups.map((group, index) => ({ ...group, id: ids[index] }));
  const context = chartCategories(groups, input.context);
  const labels = namedLabels(groups), values: number[] = [];
  const entries: { group: typeof groups[number]; observation: NumericObservation | null }[] = [];
  for (const group of groups) { if (group.observations.length) for (const observation of group.observations) entries.push({ group, observation }); else entries.push({ group, observation: null }); }
  for (const { observation } of entries) if (observation) { const value = finite(observation.value, "Observation"); if (value !== null) values.push(value); status(observation.status); }
  const width = sceneWidth(input.context), left = width < 560 ? Math.max(110, width * .34) : 185;
  const axis = axisLabel(input.axis, input.unit), domain = scale(values, left, width - 55);
  const names = entries.map(({ group, observation }) => `${group.label} [${group.id}] / ${observation?.label ?? "No observations supplied"}${observation?.status ? ` — ${statusWord(observation.status)}` : ""}`);
  const layout = rowsLayout(names, left - 30, input.context);
  const plot = domain ? rowPlot(input.title, layout.height, entries.map(({ group, observation }, index) => {
    const y = layout.rows[index].y, value = observation?.value;
    if (value === null || value === undefined) return textMarkup(labelLayout(observation?.status ? `Missing (${statusWord(observation.status)})` : "Missing", width - left - 65, input.context), left + 8, y - 10);
    const x = domain.map(value), style = categoryStyle(group.id, context);
    return `<g data-av-observation="${index}" data-av-category-id="${e(group.id)}" data-av-value="${e(value)}" data-av-x="${x}">${marker(style, x, y, `${group.label} [${group.id}] / ${observation!.label}: ${value}${observation!.status ? ` (${statusWord(observation!.status)})` : ""}`)}</g>`;
  }).join(""), layout.rows.map(row => rowLabelMarkup(row, left - 15)).join(""), domain, axis, input.context, left) : `<ul class="av-missing-observations">${entries.map(({group, observation}) => `<li>${e(group.label)} [${e(group.id)}] / ${e(observation?.label || "No observations supplied")}: Missing ${observation ? status(observation.status) + annotation(observation) : ""}</li>`).join("")}</ul>`;
  const rows = entries.map(({ group, observation }) => [identifier(group.id), labelMarkup(labels.get(group.id)!), observation ? e(observation.label) : "No observations supplied", numericText(observation?.value), observation ? status(observation.status) : "", observation ? annotation(observation) : ""]);
  return layoutRecipe(card(input, `<ul class="av-legend">${groups.map(group => markerLegend(group.id, `${group.label} [${group.id}]`, context)).join("")}</ul>${plot}${dataTable(input.title, ["Group ID", "Group", "Observation", axis, "Status", "Context"], rows)}`, "quantitative"), "distribution", input);
}

function xyLayout(xs: number[], ys: number[], xLabel: string, yLabel: string, input: { context?: TrajectoryInput["context"] }) {
  const width = sceneWidth(input.context), yTitle = labelLayout(yLabel, width - 155, input.context);
  const preliminary = scale(ys, 0, 1);
  const offsetRoom = preliminary?.offset == null ? 0 : labelLayout(`Add ${preliminary.offset} to tick labels`, width - 155, input.context).height + 14;
  const top = yTitle.height + 38 + offsetRoom, bottom = top + 260;
  const y = scale(ys, bottom, top), left = Math.max(110, ...(y?.tickLabels.map(label => labelLayout(label, width, input.context).width + 24) || [110]));
  const logicalWidth = Math.max(width, left + 180), x = scale(xs, left, logicalWidth - 55);
  const axisY = bottom + 18, height = axisY + (x ? axisHeight(x, xLabel, input.context) : 70);
  return { width: logicalWidth, height, x, y, left, top, bottom, axisY };
}
export function trajectory(input: TrajectoryInput): string {
  const ids = occurrenceIds(input.series, "Series"), xs: number[] = [], ys: number[] = [];
  const context = chartCategories(input.series.map((series, i) => ({ id: ids[i], label: series.label })), input.context);
  for (const series of input.series) {
    let previous: number | null = null;
    for (const point of series.points) {
      const x = finite(point.x, "Trajectory x"), y = finite(point.y, "Trajectory y");
      if (x !== null && previous !== null && x < previous) throw new TypeError("Trajectory x values must be supplied in nondecreasing order within each series.");
      if (x !== null) { previous = x; xs.push(x); } if (y !== null) ys.push(y);
    }
  }
  const xLabel = axisLabel(input.xAxis, input.xUnit), yLabel = axisLabel(input.yAxis, input.yUnit), layout = xyLayout(xs, ys, xLabel, yLabel, input);
  const { x, y } = layout, complete = input.series.some(series => series.points.some(point => point.x != null && point.y != null));
  const plot = x && y && complete ? svg(input.title, layout.height, yAxis(y, layout.left, yLabel, input.context?.measureText, layout.width - 55) + xAxis(x, layout.axisY, xLabel, input.context?.measureText) + input.series.map((series, index) => {
    const id = ids[index], style = categoryStyle(id, context), parts: string[] = []; let segment: string[] = [];
    const flush = () => { if (segment.length > 1) parts.push(`<polyline data-av-category-id="${e(id)}" fill="none" stroke="var(--av-series-${style.color})" stroke-width="2"${style.dash ? ` stroke-dasharray="${style.dash}"` : ""} points="${segment.join(" ")}"><title>${e(series.label)} [${e(id)}]</title></polyline>`); segment = []; };
    for (const point of series.points) { if (point.x == null || point.y == null) { flush(); continue; } segment.push(`${x.map(point.x)},${y.map(point.y)}`); } flush();
    return parts.join("") + series.points.map(point => point.x == null || point.y == null ? "" : `<g data-av-category-id="${e(id)}">${marker(style, x.map(point.x), y.map(point.y), `${series.label} [${id}] / ${point.label}: ${point.x}, ${point.y}`)}</g>`).join("");
  }).join(""), layout.width) : noPlot();
  const rows = input.series.flatMap((series, index) => series.points.length ? series.points.map(point => [identifier(ids[index]), e(series.label), e(point.label), numericText(point.x), numericText(point.y), annotation(point)]) : [[identifier(ids[index]), e(series.label), "No observations supplied", "Missing", "Missing", ""]]);
  return layoutRecipe(card(input, `<ul class="av-legend">${input.series.map((series, i) => markerLegend(ids[i], `${series.label} [${ids[i]}]`, context)).join("")}</ul>${plot}${dataTable(input.title, ["Series ID", "Series / subgroup", "Observation", xLabel, yLabel, "Context"], rows)}`, "history"), "trajectory", input);
}

export function scatterPlot(input: ScatterInput): string {
  if (input.coordinateScope !== undefined && input.coordinateScope !== "known" && input.coordinateScope !== "complete") throw new TypeError("Coordinate scope must be known or complete.");
  const ids = new Map<string, typeof input.points[number]>(), groups = new Map<string, string>();
  for (const point of input.points) {
    if (typeof point.id !== "string" || !point.id || ids.has(point.id)) throw new TypeError("Scatter point IDs must be nonempty and unique.");
    ids.set(point.id, point); finite(point.x, "Scatter x"); finite(point.y, "Scatter y");
    const id = point.groupId ?? point.group ?? "Unspecified", label = point.group ?? point.groupId ?? "Unspecified";
    if (!id || typeof id !== "string") throw new TypeError("Scatter group IDs must be nonempty strings.");
    if (groups.has(id) && groups.get(id) !== label) throw new TypeError("One scatter group ID has conflicting labels."); groups.set(id, label);
  }
  for (const frontier of input.frontiers || []) for (const id of frontier.pointIds) { const point = ids.get(id); if (!point || point.x == null || point.y == null) throw new TypeError("Frontier references must identify supplied points with complete coordinates."); }
  const context = chartCategories([...groups].map(([id, label]) => ({ id, label })), input.context);
  const xLabel = axisLabel(input.xAxis, input.xUnit), yLabel = axisLabel(input.yAxis, input.yUnit);
  const complete = input.points.filter(point => point.x != null && point.y != null), partial = input.points.filter(point => (point.x == null) !== (point.y == null)), absent = input.points.length - complete.length - partial.length;
  function cloud(scope: "known" | "complete"): string {
    const domains = scope === "known" ? input.points : complete;
    const xs = domains.flatMap(point => point.x == null ? [] : [point.x]), ys = domains.flatMap(point => point.y == null ? [] : [point.y]);
    const layout = xyLayout(xs, ys, xLabel, yLabel, input), { x, y } = layout;
    if (!x || !y || !complete.length) return '<p class="av-empty">No complete coordinate pairs. Known individual coordinates remain in the missing-coordinate bands and data.</p>';
    const paths = (input.frontiers || []).map(frontier => `<polyline fill="none" stroke="var(--av-muted)" stroke-width="2" stroke-dasharray="7 4" points="${frontier.pointIds.map(id => { const point = ids.get(id)!; return `${x.map(point.x!)},${y.map(point.y!)}`; }).join(" ")}"><title>${e(frontier.label)} — supplied connection</title></polyline>`).join("");
    return svg(input.title, layout.height, yAxis(y, layout.left, yLabel, input.context?.measureText, layout.width - 55) + xAxis(x, layout.axisY, xLabel, input.context?.measureText) + paths + input.points.map((point, index) => point.x == null || point.y == null ? "" : `<g class="av-terrain-point" data-av-inspect="point-${index}" data-av-category-id="${e(point.groupId ?? point.group ?? "Unspecified")}" aria-label="Inspect ${e(point.id)}: ${e(point.label)}"><circle class="av-point-hit" cx="${x.map(point.x)}" cy="${y.map(point.y)}" r="14" fill="transparent"/>${marker(categoryStyle(point.groupId ?? point.group ?? "Unspecified", context), x.map(point.x), y.map(point.y), `${point.id}: ${point.label} — ${point.x}, ${point.y}`)}</g>`).join(""), layout.width);
  }
  const selected = input.coordinateScope || "known";
  const scopeControls = partial.length ? '<div class="av-coordinate-controls av-button-group" data-av-controls hidden role="group" aria-label="Coordinate scope"><button type="button" class="av-button" data-av-scope-choice="known">All known coordinates</button><button type="button" class="av-button" data-av-scope-choice="complete">Complete pairs only</button></div>' : "";
  const clouds = `<div data-av-coordinate-scope="known"${selected === "known" ? "" : " hidden"}><p class="av-note">Scale includes every supplied known coordinate. This plot shows ${complete.length} complete ${complete.length === 1 ? 'pair' : 'pairs'}.${partial.length ? ` ${partial.length} partial ${partial.length === 1 ? 'observation appears' : 'observations appear'} in the separate missing-coordinate bands.` : ""}${absent ? ` ${absent} ${absent === 1 ? 'observation has' : 'observations have'} neither coordinate and ${absent === 1 ? 'remains' : 'remain'} in the complete data.` : ""}</p>${cloud("known")}</div>` + (partial.length || selected === "complete" ? `<div data-av-coordinate-scope="complete"${selected === "complete" ? "" : " hidden"}><p class="av-note">Complete-pairs scope: ${complete.length} paired ${complete.length === 1 ? 'observation' : 'observations'}.${partial.length ? ` ${partial.length} partial ${partial.length === 1 ? 'observation remains' : 'observations remain'} below and in the complete data.` : ""}</p>${cloud("complete")}</div>` : "");
  const bands = (["x", "y"] as const).map(axis => {
    const entries = input.points.map((point, index) => ({ point, index })).filter(({ point }) => point[axis] != null && point[axis === "x" ? "y" : "x"] == null);
    if (!entries.length) return "";
    const width = sceneWidth(input.context), left = width < 560 ? Math.max(110, width * .34) : 185, domain = scale(input.points.flatMap(point => point[axis] == null ? [] : [point[axis]!]), left, width - 55)!;
    const names = entries.map(({ point }) => `${point.label} [${point.id}]`), layout = rowsLayout(names, left - 30, input.context), label = `${axis === "x" ? "Y" : "X"} not observed — known ${axis === "x" ? xLabel : yLabel}`;
    return `<section class="av-missing-coordinate-band"><h3>${e(label)}</h3>${rowPlot(label, layout.height, entries.map(({ point, index }, row) => `<g data-av-inspect="point-${index}" data-av-partial-coordinate="${axis}" data-av-category-id="${e(point.groupId ?? point.group ?? "Unspecified")}">${marker(categoryStyle(point.groupId ?? point.group ?? "Unspecified", context), domain.map(point[axis]!), layout.rows[row].y, `${point.label}: ${point[axis]}; ${axis === "x" ? "Y" : "X"} missing`)}</g>`).join(""), layout.rows.map(row => rowLabelMarkup(row, left - 15)).join(""), domain, axis === "x" ? xLabel : yLabel, input.context, left)}</section>`;
  }).join("");
  const inspector = `<details class="av-inspector" open><summary>Inspect observations</summary>${input.points.map((point, index) => objectDetail(`point-${index}`, `${point.label} · ${point.id}`, `<dl class="av-facts"><div><dt>Identity</dt><dd>${identifier(point.id)}</dd></div><div><dt>Group</dt><dd>${e(point.group ?? point.groupId ?? "Unspecified")} ${identifier(point.groupId ?? point.group ?? "Unspecified")}</dd></div><div><dt>${e(xLabel)}</dt><dd>${numericText(point.x)}</dd></div><div><dt>${e(yLabel)}</dt><dd>${numericText(point.y)}</dd></div></dl>${annotation(point)}`, index === 0)).join("")}</details>`;
  const frontierTable = input.frontiers?.length ? dataTable("Supplied frontier connections", ["Connection", "Point IDs and labels in supplied order", "Context"], input.frontiers.map(frontier => [e(frontier.label), `<ol>${frontier.pointIds.map(id => `<li>${identifier(id)} — ${e(ids.get(id)!.label)}</li>`).join("")}</ol>`, annotation(frontier)])) : "";
  const body = `<div class="av-terrain" data-av-explorer>${explorerControls("Observation", input.points.map((point, i) => ({ key: `point-${i}`, label: `${point.label} · ${point.id}` })))}<ul class="av-legend">${[...groups].map(([id, label]) => markerLegend(id, `${label} [${id}]`, context)).join("")}</ul>${scopeControls}<div class="av-explorer"><div class="av-scatter-scenes">${clouds}${bands}${absent ? `<p class="av-missing">${absent} observations have neither coordinate; their identities and context remain in the complete data.</p>` : ""}</div>${inspector}</div></div>`;
  return layoutRecipe(card(input, body + dataTable(input.title, ["Point ID", "Label", "Group ID", "Group", xLabel, yLabel, "Context"], input.points.map(point => [identifier(point.id), e(point.label), identifier(point.groupId ?? point.group ?? "Unspecified"), e(point.group ?? point.groupId ?? "Unspecified"), numericText(point.x), numericText(point.y), annotation(point)])) + frontierTable, "quantitative"), "scatter", input);
}
