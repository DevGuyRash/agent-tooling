// The quantitative comparison views (metric, scorecard, difference and
// hierarchy) over small hand-checked comparisons, checked against the built
// bundle. Exact intervals belong to the statistics' own tests; these cases check
// what each view draws, what it says, and that nothing supplied becomes markup.
"use strict";
const H = require("./harness.cjs");
const { test } = H;

const V = H.loadVisuals();
const render = (block, comparison, spec = {}) => V.renderBlock(block, V.createContext({ ...spec, comparison }, spec.cases || {}));
const rows = (html, cls = "av-cmp-row") => H.count(html, `class="${cls}`);

// Two sandwiches rated by three people, on every metric kind.
const sandwich = () => ({
  baseline: "pb",
  alternatives: [{ id: "pb", label: "Peanut butter" }, { id: "jelly", label: "Jelly" }],
  metrics: [
    { id: "taste", label: "Taste", kind: "ordinal", levels: ["Bad", "Okay", "Good", "Great"], better: "higher", primary: true },
    { id: "again", label: "Would make again", kind: "binary" },
    { id: "minutes", label: "Time to make", kind: "numeric", unit: "min" },
    { id: "pick", label: "Picked", kind: "preference" },
    { id: "place", label: "Place", kind: "rank" },
  ],
  observations: [
    ...["Ana", "Ben", "Cy"].flatMap((u, i) => [
      { alternative: "pb", metric: "taste", value: ["Great", "Good", "Good"][i], unit: u },
      { alternative: "jelly", metric: "taste", value: ["Okay", "Good", "Bad"][i], unit: u },
      { alternative: "pb", metric: "minutes", value: [3, 4, 3.5][i], unit: u },
      { alternative: "jelly", metric: "minutes", value: [2, 2.5, 3][i], unit: u },
    ]),
    { alternative: "pb", metric: "again", value: true }, { alternative: "pb", metric: "again", value: true },
    { alternative: "pb", metric: "again", value: true }, { alternative: "pb", metric: "again", value: false },
    { alternative: "jelly", metric: "again", value: true }, { alternative: "jelly", metric: "again", value: null, valid: false, invalid_reason: "did not finish" },
  ],
  preferences: [{ a: "pb", b: "jelly", winner: "pb", metric: "pick" }, { a: "pb", b: "jelly", winner: "pb", metric: "pick" }, { a: "pb", b: "jelly", winner: "tie", metric: "pick" }],
  rankings: [{ order: ["pb", "jelly"], metric: "place" }, { order: ["jelly", "pb"], metric: "place" }, { order: ["pb", "jelly"], metric: "place" }],
});

// Two directions with two concepts each; Direction A converts far better.
const nested = () => {
  const alternatives = [], observations = [];
  const groups = [["Direction A", "Concept 1"], ["Direction A", "Concept 2"], ["Direction B", "Concept 3"], ["Direction B", "Concept 4"]];
  groups.forEach((g, gi) => [0, 1].forEach(j => {
    const id = `ad${gi * 2 + j + 1}`;
    alternatives.push({ id, label: `Ad ${gi * 2 + j + 1}`, group: g });
    ["north", "south"].forEach(c => observations.push({ alternative: id, metric: "conv", case: c, value: gi < 2 ? 80 : 20, n: 200 }));
  }));
  return { alternatives, observations, baseline: "ad1", cases: [{ id: "north", label: "North" }, { id: "south", label: "South" }], metrics: [{ id: "conv", label: "Conversion", kind: "count", better: "higher" }] };
};

// ------------------------------------------------------------------ framing and notices

test("every view sits in a frame and says so when there is no comparison", () => {
  for (const type of ["metric", "scorecard", "difference", "hierarchy"]) {
    const html = V.renderBlock({ type, title: "T" }, V.createContext({}, {}));
    H.includes(html, `<section class="av-block av-block--${type}"`, `${type} frame`);
    H.includes(html, "No comparison to show", `${type} notice`);
  }
});

test("an unknown metric is a visible problem naming the metrics there are", () => {
  const html = render({ type: "metric", metric: "nope" }, sandwich());
  H.includes(html, "av-cmp-problems");
  H.includes(html, "No metric “nope”");
  H.includes(html, "taste, again, minutes, pick, place");
});

test("unknown alternatives and an absent baseline are listed, not dropped silently", () => {
  const html = render({ type: "metric", metric: "again", alternatives: ["jelly", "ghost"], baseline: "pb" }, sandwich());
  H.includes(html, "Not among the alternatives: ghost");
  H.includes(html, "The baseline “pb” is not among the alternatives shown");
  H.equal(rows(html), 1, "one row for the one known alternative");
});

test("a block's own data is drawn, with its alternatives' labels", () => {
  const html = V.renderBlock({ type: "metric", metric: "again", data: sandwich() }, V.createContext({}, {}));
  H.includes(html, "Peanut butter");
  H.includes(html, 'data-arm="jelly"');
});

// ------------------------------------------------------------------ metric, by kind

test("binary: the share of valid observations, the count beside it, invalid ones counted apart", () => {
  const html = render({ type: "metric", metric: "again" }, sandwich());
  H.includes(html, "75%", "3 of 4 yes as a share");
  H.includes(html, "3/4", "the count behind the share");
  H.includes(html, "1/1", "the invalid observation is not a failure");
  H.includes(html, "1 invalid");
  H.includes(html, '<span class="av-ci"></span>', "an interval is drawn");
  H.includes(html, "av-cmp-few", "few observations are marked");
});

test("numeric: one dot per valid value, the mean with its interval, the median named", () => {
  const html = render({ type: "metric", metric: "minutes" }, sandwich());
  H.equal(H.count(html, 'class="av-cmp-dot"'), 6, "dots");
  H.includes(html, "3.5 min", "peanut butter's mean with its unit");
  H.includes(html, "median 2.5");
  H.includes(html, "av-cmp-med");
});

test("numeric with center median: the median leads and no interval is claimed for it", () => {
  const html = render({ type: "metric", metric: "minutes", center: "median" }, sandwich());
  H.includes(html, "mean 3.5");
  H.excludes(html, "av-legend-ci", "interval legend");
});

test("ordinal: diverging level bars with counts, the median level named, no score", () => {
  const html = render({ type: "metric", metric: "taste" }, sandwich());
  H.equal(H.count(html, 'class="av-cmp-lk"'), 2, "one bar per alternative");
  H.includes(html, "Good: 2 (67%)", "peanut butter's Good count");
  H.includes(html, "Bad: 1 (33%)", "jelly's Bad count");
  for (const level of ["Bad", "Okay", "Good", "Great"]) H.includes(html, `${level}</span>`, `legend level ${level}`);
  H.excludes(html, 'class="av-pt"', "a point for an ordinal mean");
});

test("rank: mean position with circles for the share placed at each position", () => {
  const html = render({ type: "metric", metric: "place" }, sandwich());
  H.ok(H.count(html, 'class="av-cmp-bub"') >= 3, "position circles");
  H.includes(html, "1st in");
  H.includes(html, ">1st<", "axis starts at first place");
});

test("preference: win rate over decisive judgments, ties counted, 50% marked", () => {
  const html = render({ type: "metric", metric: "pick" }, sandwich());
  H.includes(html, "2 won · 0 lost · 1 tied");
  H.includes(html, "av-cmp-ref--even");
});

test("direction: better or worse only when the metric has one and the interval excludes zero", () => {
  const data = nested();
  const directed = render({ type: "metric", metric: "conv" }, data);
  H.includes(directed, "worse than baseline", "Direction B against the Direction A baseline");
  H.includes(directed, "higher is better");
  data.metrics[0].better = undefined;
  const neutral = render({ type: "metric", metric: "conv" }, data);
  H.excludes(neutral, "than baseline", "a tone without a direction");
  H.excludes(neutral, "is better");
});

test("thresholds: the metric's own, an override with its label, or none", () => {
  const data = nested();
  data.metrics[0].threshold = 0.2;
  H.includes(render({ type: "metric", metric: "conv" }, data), "av-cmp-ref--rule");
  const labelled = render({ type: "metric", metric: "conv", threshold: { value: 0.3, label: "Break-even" } }, data);
  H.includes(labelled, "Break-even");
  H.excludes(render({ type: "metric", metric: "conv", threshold: null }, data), "av-cmp-ref--rule", "a hidden threshold");
});

test("by case: one panel per case on a shared scale; by group: pooled group rows over members", () => {
  const byCase = render({ type: "metric", metric: "conv", by: "case" }, nested());
  H.equal(H.count(byCase, 'class="av-cmp-panel"'), 2, "panels");
  H.includes(byCase, "North");
  const byGroup = render({ type: "metric", metric: "conv", by: "group" }, nested());
  H.equal(rows(byGroup, "av-cmp-row av-cmp-row--group"), 2, "outermost groups only by default");
  H.equal(rows(byGroup, "av-cmp-row av-cmp-row--alt"), 8, "every member");
});

test("an alternative without observations shows that, rather than a value", () => {
  const data = sandwich();
  data.alternatives.push({ id: "toast", label: "Toast" });
  const html = render({ type: "metric", metric: "again" }, data);
  H.includes(html, "no observations");
});

test("sort by value orders best first when the metric has a direction", () => {
  const html = render({ type: "metric", metric: "conv", sort: "value", baseline: "ad8" }, nested());
  H.ok(html.indexOf('data-arm="ad1"') < html.indexOf('data-arm="ad8"'), "Direction A before Direction B");
});

// ------------------------------------------------------------------ scorecard

test("scorecard: alternatives across, baseline column marked, missing cells shown", () => {
  const data = sandwich();
  data.alternatives.push({ id: "toast", label: "Toast" });
  const html = render({ type: "scorecard" }, data);
  H.includes(html, 'class="av-scroll-x av-sc-wrap" tabindex="0" role="region"', "a keyboard-reachable scroll region");
  H.equal(H.count(html, "av-sc-alt--base"), 1, "the baseline header");
  H.equal(H.count(html, "av-sc-cell--base"), 5, "a baseline cell per metric");
  H.equal(H.count(html, "av-sc-cell--missing"), 5, "toast has nothing on any metric");
  H.includes(html, 'scope="row" class="av-sc-metric"', "metrics as row headers");
});

test("scorecard: tints only where a direction and the baseline make better or worse meaningful", () => {
  const data = nested();
  const html = render({ type: "scorecard" }, data);
  H.ok(H.count(html, 'data-tone="worse"') >= 4, "Direction B is worse than the Direction A baseline");
  H.includes(html, "worse than the baseline");
  data.metrics[0].better = "none";
  H.excludes(render({ type: "scorecard" }, data), "data-tone=", "a tint without a direction");
  delete data.baseline;
  data.metrics[0].better = "higher";
  H.excludes(render({ type: "scorecard" }, data), "data-tone=", "a tint without a baseline");
});

test("scorecard: group headers span their members; many alternatives turn into rows", () => {
  const html = render({ type: "scorecard" }, nested());
  H.includes(html, 'colspan="4" class="av-sc-group"', "a direction spans four columns");
  H.includes(html, 'colspan="2" class="av-sc-group"', "a concept spans two");
  const data = nested();
  for (let i = 9; i <= 12; i++) data.alternatives.push({ id: `ad${i}`, group: ["Direction C"] });
  const tall = render({ type: "scorecard" }, data);
  H.includes(tall, 'data-orient="rows"');
  H.includes(tall, 'scope="rowgroup"');
});

// ------------------------------------------------------------------ difference

test("difference: each alternative minus the baseline, a zero line and a plain reading", () => {
  const data = { baseline: "old", alternatives: [{ id: "old" }, { id: "new" }, { id: "same" }], metrics: [{ id: "ok", kind: "count" }],
    observations: [{ alternative: "old", metric: "ok", value: 0, n: 20 }, { alternative: "new", metric: "ok", value: 20, n: 20 }, { alternative: "same", metric: "ok", value: 0, n: 20 }] };
  const html = render({ type: "difference" }, data);
  H.equal(H.count(html, 'class="av-cmp-drow'), 2, "two rows against the baseline");
  H.includes(html, "av-cmp-zero");
  H.includes(html, "The 95% interval lies above zero:", "20/20 against 0/20");
  H.includes(html, "The 95% interval includes zero:", "0/20 against 0/20");
  H.includes(html, "+100 pts");
  H.ok(/<details class="av-cmp-method">[\s\S]*<li>[^<]+<\/li>/.test(html), "the statistics' method in words");
});

test("difference: every pair, explicit pairs, and identical alternatives as chance alone", () => {
  const data = sandwich();
  data.alternatives.push({ id: "pb2", label: "Peanut butter again" });
  data.observations.push({ alternative: "pb2", metric: "again", value: true }, { alternative: "pb2", metric: "again", value: false });
  const all = render({ type: "difference", metric: "again", pairs: "all", identical: false }, data);
  H.equal(H.count(all, 'class="av-cmp-drow'), 3, "three pairs");
  const named = render({ type: "difference", metric: "again", pairs: [["jelly", "pb"], ["pb", "pb"]] }, data);
  H.equal(H.count(named, 'class="av-cmp-drow'), 1, "one valid pair");
  H.includes(named, "A pair names two different alternatives shown");
  const noise = render({ type: "difference", metric: "again", identical: [["pb", "pb2"]] }, data);
  H.includes(noise, "Chance alone");
  H.includes(noise, "av-cmp-drow av-cmp-drow--noise");
});

test("difference: a threshold in difference units, and one panel per metric", () => {
  const html = render({ type: "difference", metric: "again", threshold: { value: 0.1, label: "Worth it" } }, sandwich());
  H.includes(html, "av-cmp-thr");
  H.includes(html, "Worth it");
  const multi = render({ type: "difference", metrics: ["taste", "again", "minutes"], threshold: 0.1 }, sandwich());
  H.equal(H.count(multi, 'class="av-cmp-dpanel"'), 3, "panels");
  H.includes(multi, "drawn only when the block shows one metric");
  H.includes(multi, "P(higher) − ½", "ordinal differences in their own terms");
});

// ------------------------------------------------------------------ hierarchy

test("hierarchy: nested pooled groups, their members, and differences at each level", () => {
  const html = render({ type: "hierarchy" }, nested());
  H.equal(rows(html, "av-cmp-row av-cmp-row--group"), 6, "two directions and four concepts");
  H.equal(rows(html, "av-cmp-row av-cmp-row--alt"), 8, "every alternative once");
  H.includes(html, "Between top-level groups");
  H.includes(html, "Between Direction A");
  H.includes(html, "Direction A <span class=\"av-cmp-minus\">minus</span> Direction B");
  H.includes(html, "excludes 0 · better", "Direction A converts better than B");
  H.includes(html, "av-cmp-ref--parent", "members read against their group");
  H.includes(html, "4 alternatives in 2 groups, pooled");
});

test("hierarchy: depth folds deeper groups; no groups is said plainly", () => {
  const shallow = render({ type: "hierarchy", depth: 1 }, nested());
  H.equal(rows(shallow, "av-cmp-row av-cmp-row--group"), 2, "directions only");
  const flat = render({ type: "hierarchy", metric: "again" }, sandwich());
  H.includes(flat, "No alternative names a group");
  H.equal(rows(flat, "av-cmp-row av-cmp-row--alt"), 2);
});

test("a group filter narrows to one branch and says so", () => {
  const html = render({ type: "metric", metric: "conv", groups: ["Direction B"] }, nested());
  H.equal(rows(html), 4, "Direction B's four alternatives");
  H.includes(html, "alternatives in Direction B");
  H.excludes(html, 'data-arm="ad1"');
});

test("thirty alternatives in four nested groups across ten cases render whole", () => {
  const alternatives = [], observations = [];
  for (let i = 0; i < 30; i++) {
    alternatives.push({ id: `a${i}`, group: [i < 15 ? "A" : "B", `c${Math.floor(i / 8)}`] });
    for (let c = 0; c < 10; c++) observations.push({ alternative: `a${i}`, metric: "m", case: `s${c}`, value: (i * 7 + c * 3) % 11 });
  }
  const data = { alternatives, observations, metrics: [{ id: "m", kind: "numeric" }] };
  for (const type of ["metric", "scorecard", "hierarchy", "difference"]) {
    const html = render({ type, by: type === "metric" ? "case" : undefined }, data);
    H.excludes(html, "av-block-error", `${type} error`);
    H.excludes(html, "NaN", `${type} NaN`);
  }
  H.equal(rows(render({ type: "metric" }, data)), 30, "a row per alternative");
});

// ------------------------------------------------------------------ escaping

test("every supplied text is escaped, and style attributes carry only computed values", () => {
  const X = `<img src=x onerror=alert(1)>"'&`;
  const data = {
    baseline: `a${X}`,
    alternatives: [{ id: `a${X}`, label: `L${X}`, note: `N${X}`, group: [`G${X}`, `H${X}`] }, { id: "b", label: "B", group: [`G2${X}`] }],
    cases: [{ id: `c${X}`, label: `C${X}`, group: [`R${X}`] }],
    metrics: [
      { id: `m${X}`, label: `M${X}`, kind: "numeric", unit: `U${X}`, description: `D${X}`, better: "higher" },
      { id: "o", label: "O", kind: "ordinal", levels: [`low${X}`, `high${X}`] },
    ],
    observations: [
      { alternative: `a${X}`, metric: `m${X}`, case: `c${X}`, value: 1 }, { alternative: `a${X}`, metric: `m${X}`, case: `c${X}`, value: 3 },
      { alternative: "b", metric: `m${X}`, case: `c${X}`, value: 5 }, { alternative: "b", metric: `m${X}`, case: `c${X}`, value: 9 },
      { alternative: `a${X}`, metric: "o", value: `low${X}` }, { alternative: "b", metric: "o", value: `high${X}` },
    ],
  };
  const blocks = [
    { type: "metric", by: "case", threshold: { value: 2, label: `T${X}` } }, { type: "metric", by: "group" }, { type: "metric", metric: "o" },
    { type: "scorecard" }, { type: "scorecard", orient: "rows" }, { type: "difference", threshold: { value: 1, label: `T${X}` } },
    { type: "difference", pairs: [[`a${X}`, "b"], [`z${X}`]] }, { type: "hierarchy" }, { type: "metric", metric: `nope${X}` },
    { type: "metric", alternatives: [`ghost${X}`, "b"], cases: [`k${X}`], groups: [`G2${X}`] },
  ];
  for (const b of blocks) {
    const html = render({ ...b, title: `Ti${X}`, description: `De${X}`, note: `No${X}` }, data);
    const where = `${b.type} ${JSON.stringify(b).slice(0, 60)}`;
    H.excludes(html, "<img", `${where}: raw markup`);
    H.excludes(html, `"'&`, `${where}: unescaped quotes`);
    H.includes(html, "&lt;img src=x onerror=alert(1)&gt;&quot;&#39;&amp;", `${where}: escaped text`);
    for (const m of html.matchAll(/style="([^"]*)"/g)) if (/[<>'&]|url\(|expression|NaN|undefined/i.test(m[1])) H.fail(`${where}: unexpected style text: ${m[1]}`);
  }
});

test("numbers that are not finite never reach markup", () => {
  const data = { alternatives: [{ id: "a" }, { id: "b" }], metrics: [{ id: "m", kind: "count", threshold: Infinity }],
    observations: [{ alternative: "a", metric: "m", value: NaN, n: 10 }, { alternative: "b", metric: "m", value: 3, n: Infinity }],
    aggregates: [{ alternative: "a", metric: "m", k: -1, n: 2.5 }] };
  for (const type of ["metric", "scorecard", "difference", "hierarchy"]) {
    const html = render({ type, threshold: NaN }, data);
    H.excludes(html, "av-block-error", `${type} error`);
    H.excludes(html, "NaN", `${type} NaN`);
    H.excludes(html, "Infinity", `${type} Infinity`);
  }
});

test("unequal case coverage is named, and data naming no case gets no empty case panels", () => {
  const data = {
    alternatives: [{ id: "a", label: "Alpha" }, { id: "b", label: "Beta" }],
    cases: [{ id: "x", label: "Morning" }, { id: "y", label: "Evening" }],
    metrics: [{ id: "m", kind: "binary", better: "higher" }, { id: "s", label: "Seats", kind: "count" }],
    observations: [
      { alternative: "a", metric: "m", case: "x", value: true }, { alternative: "a", metric: "m", case: "y", value: false },
      { alternative: "b", metric: "m", case: "x", value: true },
      { alternative: "a", metric: "s", value: 3, n: 5 }, { alternative: "b", metric: "s", value: 4, n: 5 },
    ],
  };
  for (const type of ["metric", "scorecard", "difference", "hierarchy"]) {
    const html = render({ type, metric: "m", ...(type === "difference" ? { pairs: [["a", "b"]] } : {}) }, data);
    H.includes(html, "Unequal cases", `${type} names unequal coverage`);
    H.includes(html, "Beta has no data for Evening", `${type} names the missing case`);
  }
  H.excludes(render({ type: "metric", metric: "m", cases: ["x"] }, data), "Unequal cases", "a shared-case filter removes the note");
  const seats = render({ type: "metric", metric: "s", by: "case" }, data);
  H.includes(seats, "No observation names a case", "caseless data says so");
  data.observations.push({ alternative: "a", metric: "s", case: "x", value: 1, n: 2 });
  H.includes(render({ type: "metric", metric: "s", by: "case" }, data), "2 of 3 entries for Seats name no case", "partly caseless data is counted");
  H.excludes(seats, "av-cmp-multiples\"", "no empty case panels");
});

test("a comparison of totals alone still lists the totals it was given", () => {
  const spec = V.comparisonReport({ alternatives: [{ id: "a" }, { id: "b" }], metrics: [{ id: "m", kind: "count" }], aggregates: [{ alternative: "a", metric: "m", k: 1, n: 4 }, { alternative: "b", metric: "m", k: 2, n: 4 }] }, {});
  H.ok(spec.sections.some(s => s.id === "observations" && s.title === "Every supplied total"), "a totals section");
});

H.report();
