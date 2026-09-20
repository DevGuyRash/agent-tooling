/** Fictional study: all observations and judgments are synthetic demonstration inputs. */
import * as V from "../src/index";

const source = [{ label: "Field study record", href: "#synthetic-evidence", note: "Synthetic demonstration input." }];
const alternatives: V.Named[] = [
  { id: "fieldbook", label: "Fieldbook", note: "A local notebook with an explicit export step." },
  { id: "relay", label: "Relay", note: "A shared notebook built around a network connection." },
  { id: "archive", label: "Archive Kit", note: "A prepared offline bundle with a later merge step." },
];
const chartContext = V.createChartContext({ categories: alternatives, width: 1120 });
const dimensions: V.Named[] = [
  { id: "offline", label: "Capture without a signal" },
  { id: "recover", label: "Recover the original record" },
  { id: "share", label: "Hand the work to the next team" },
];
const findings: V.MatrixInput["findings"] = [
  { alternative: "fieldbook", dimension: "offline", value: "All ten supplied notes saved locally", status: "supported", evidence: source },
  { alternative: "fieldbook", dimension: "recover", value: "Original text and attachments retained", status: "supported" },
  { alternative: "fieldbook", dimension: "share", value: "Export and transfer required", status: "conditional", note: "The next team must receive the bundle." },
  { alternative: "relay", dimension: "offline", value: "Two notes remained unsaved", status: "failed", evidence: source },
  { alternative: "relay", dimension: "recover", value: "Originals available after successful sync", status: "conditional" },
  { alternative: "relay", dimension: "share", value: "Shared workspace opens directly", status: "supported" },
  { alternative: "archive", dimension: "offline", value: "Works with the prepared bundle", status: "conditional", note: "Required maps and reference files must be packed before departure." },
  { alternative: "archive", dimension: "share", value: "Merge into the shared archive", status: "conditional" },
];
const matrix = { title: "What each option actually supports", alternatives, dimensions, findings, evidence: source };
const tradeoff: V.ScatterInput = {
  context: chartContext,
  title: "Fast capture, or less work later?", description: "Fieldbook captured a note sooner; Relay took less handoff preparation in its connected session. Archive Kit has no measured handoff duration.",
  xAxis: "Capture time", xUnit: "s", yAxis: "Handoff preparation", yUnit: "min",
  points: [
    { id: "fieldbook", label: "Fieldbook", x: 7, y: 12, groupId: "fieldbook", group: "Local capture", evidence: source },
    { id: "relay", label: "Relay", x: 12, y: 6, groupId: "relay", group: "Shared workspace", note: "Timing in a connected session; offline failure still applies." },
    { id: "archive", label: "Archive Kit", x: 3, y: null, groupId: "archive", group: "Prepared bundle", note: "Handoff preparation was not measured." },
  ],
};
const lineage: V.LineageInput = {
  context: chartContext,
  title: "Follow a claim back to its grounds", description: "The disconnected session supports the short pilot. The larger-attachment objection limits how far that conclusion extends.",
  nodes: [
    { id: "assignment", label: "Field assignment", kind: "requirement", detail: "Capture notes without a connection and retain original records." },
    { id: "record", label: "Disconnected session", kind: "observation", detail: "Ten notes saved in Fieldbook; two unsaved in Relay.", evidence: source },
    { id: "claim", label: "Offline suitability", kind: "claim", detail: "Fieldbook met the supplied offline task; Relay did not." },
    { id: "objection", label: "Larger attachments", kind: "objection", detail: "The available session does not cover a full day of large photographs." },
    { id: "decision", label: "A bounded pilot", kind: "decision", detail: "Use Fieldbook for the short pilot, retaining the export condition." },
  ],
  edges: [
    { from: "assignment", to: "claim", relation: "sets the requirement" },
    { from: "record", to: "claim", relation: "supports within this session", evidence: source },
    { from: "objection", to: "claim", relation: "limits transfer to longer use" },
    { from: "claim", to: "decision", relation: "informs" },
    { from: "objection", to: "decision", relation: "limits scope" },
  ],
};
const unknowns: V.UnknownsInput = {
  title: "What could still change the choice?", alternatives,
  issues: [
    { label: "A full day of large attachments", relevance: "Material for longer trips; the short pilot does not settle it.", affected: [{ alternative: "fieldbook", consequence: "Storage and recovery behavior remain unknown." }, { alternative: "archive", consequence: "Prepared-bundle limits remain unknown." }], evidence: source },
    { label: "Archive Kit recovery", relevance: "Original-record recovery is a requirement, not a convenience.", affected: [{ alternative: "archive", consequence: "Its empty requirement cell must remain unresolved." }] },
    { label: "Handoff effort", relevance: "Matters when the next team has little preparation time.", affected: [{ alternative: "archive", consequence: "No handling measurement is available." }] },
  ],
};
const scenarios: V.ScenarioInput = {
  title: "Change the conditions. Keep the evidence.", description: "These are supplied situations and their recorded implications, not a predictive model.",
  scenarios: [
    { label: "No signal in the field", condition: "A short trip, ten notes, and no network connection.", outcomes: [{ alternative: "Fieldbook", outcome: "Suitable for the bounded pilot; export before handoff.", status: "conditional" }, { alternative: "Relay", outcome: "Two unsaved notes fail the capture requirement.", status: "failed" }, { alternative: "Archive Kit", outcome: "Prepared inputs work; original recovery remains unverified.", status: "uncertain" }], evidence: source },
    { label: "Connected collaboration", condition: "A stable connection is available and immediate sharing matters.", outcomes: [{ alternative: "Fieldbook", outcome: "The manual export remains a handling cost.", status: "conditional" }, { alternative: "Relay", outcome: "Direct sharing is useful under this condition.", status: "supported" }, { alternative: "Archive Kit", outcome: "Prepared bundles add an unmeasured merge step.", status: "uncertain" }], tradeoff },
    { label: "A longer remote trip", condition: "Large image sets, a full day of capture, and no connection.", outcomes: alternatives.map(a => ({ alternative: a.label, outcome: "The retained observations do not establish this operating condition.", status: "missing" as const })), note: "Changing the task can make the current evidence insufficient." },
  ],
};
const recommendations: V.ConditionalInput = {
  title: "Where each choice fits",
  items: [
    { condition: "Short, disconnected pilot", implication: "Use Fieldbook and include its export bundle in the handoff.", status: "conditional", evidence: source },
    { condition: "Connected work with immediate sharing", implication: "Relay remains a reasonable alternative under this different operating condition.", status: "conditional" },
    { condition: "Long remote trip with large images", implication: "The available evidence does not yet support a choice.", status: "missing" },
  ],
};
const artifacts: V.ArtifactInput = {
  title: "The records behind the view", description: "Inspect native text and compare the details that a summary can lose.",
  artifacts: [
    { label: "Fieldbook / local save record", mediaType: "text/plain", text: "session: disconnected-small\nnotes attempted: 10\nnotes retained: 10\nattachments: retained\nhandoff: export bundle required", evidence: source },
    { label: "Relay / local save record", mediaType: "text/plain", text: "session: disconnected-small\nnotes attempted: 10\nnotes retained: 8\npending notes: 2\nnetwork: unavailable\nresult: incomplete", evidence: source },
    { label: "Archive Kit / preparation note", mediaType: "text/plain", text: 'maps: embedded\nreference files: embedded\ncapture: local\noriginal recovery: not observed\nhandoff duration: not recorded\nliteral user note: <script> is text, not code', note: "Missing observations stay missing." },
  ],
};

function grid(...fragments: string[]): string { return `<div class="av-panel-grid">${fragments.join("")}</div>`; }
function wide(fragment: string): string { return `<div class="av-span-full">${fragment}</div>`; }

export function renderDemo(): string {
  const views: V.WorkspaceView[] = [
    { id: "overview", label: "The decision", description: "A short pilot, three alternatives, and the conditions that matter.", icon: "overview", body: grid(
      wide(V.storyPanel({ id: "pilot-conclusion", title: "Use Fieldbook for the short pilot", collapsible: false,
        lead: [{ text: "Fieldbook retained all ten notes offline", tone: "positive", strong: true }, { text: ". The next team needs the export bundle before it can use them." }],
        paragraphs: ["That supports this short pilot. It does not establish that a full day with large images will work; those conditions were not observed."],
        takeaways: [
          { label: "The capture worked", text: "Ten notes and their attachments were retained in the disconnected session.", status: "supported", evidence: source },
          { label: "Include the handoff", text: [{ text: "Export before transfer.", tone: "caution", strong: true }, { text: " The local capture and the next team's usable copy are separate outcomes." }], status: "conditional" },
          { label: "Longer trips remain open", text: "Large image sets and all-day use need their own evidence.", status: "uncertain" },
        ],
      })),
      wide(V.conditionalRecommendations(recommendations)),
      V.evidenceExcerpts({ title: "The assignment", items: [{ label: "The field team's request", text: "We need to capture notes when there is no signal, keep the original records, and hand the work to another team. Choose something suitable for a short pilot. Tell us what could change that choice.", context: "A fictional operational decision", evidence: source }] }),
      V.uncertaintyPanel({ title: "The boundary of the recommendation", items: [{ label: "Short pilot only", reason: "Large image sets and all-day use were not observed.", status: "uncertain" }, { label: "Handoff is part of use", reason: "Fieldbook's export step is required for the next team.", status: "conditional" }] }),
      wide(V.comparisonJourney({ ...matrix, title: "Meet the alternatives", description: "Step through each approach and inspect the original requirement findings." })),
    ) },
    { id: "requirements", label: "Requirements", description: "Inspect adequacy before preference.", icon: "compare", body:
      V.annotatedTable({ title: "The alternatives at a glance", columns: ["Alternative", "Operating approach", "Important condition"], rows: [[{ value: "Fieldbook" }, { value: "Local capture" }, { value: "Export before handoff", status: "conditional" }], [{ value: "Relay" }, { value: "Shared workspace" }, { value: "Needs a connection for the supplied task", status: "failed" }], [{ value: "Archive Kit" }, { value: "Prepared offline bundle" }, { value: "Original recovery is unverified", status: "missing" }]] }) +
      V.comparisonMatrix({ ...matrix, id: "requirement-findings", limitations: ["The blank recovery cell for Archive Kit is an unresolved requirement."] }) +
      grid(V.constraintMap({ ...matrix, title: "Which requirements are met?" }), V.constraintSatisfaction({ ...matrix, title: "Conditions travel with each finding" })),
    },
    { id: "measurements", label: "Measurements", description: "Individual observations, ranges, and repeated rounds.", icon: "plot", body:
      V.pairedComparison({ context: chartContext, title: "Preparation changed the observed capture time", axis: "Capture time", unit: "s", leftLabel: "Unprepared", rightLabel: "Prepared", pairs: [{ label: "Fieldbook", left: 11, right: 7, evidence: source }, { label: "Relay", left: 12, right: 12 }, { label: "Archive Kit", left: null, right: 3, note: "The unprepared attempt was not timed." }] }) +
      V.intervalPlot({ context: chartContext, title: "Supplied timing ranges", axis: "Capture time", unit: "s", intervalLabel: "Observed minimum and maximum in the supplied sessions", items: [{ label: "Fieldbook", low: 7, high: 11, estimate: 9, note: "The midpoint is supplied by the fictional study, not estimated by the renderer." }, { label: "Relay", low: 10, high: 19, note: "No central estimate was supplied." }, { label: "Archive Kit", estimate: 3, note: "One observation; range unavailable." }] }) +
      V.distribution({ context: chartContext, title: "The slow and incomplete sessions remain visible", axis: "Capture time", unit: "s", groups: [{ id: "fieldbook", label: "Fieldbook", observations: [{ label: "Session 1", value: 7 }, { label: "Session 2", value: 9 }, { label: "Session 3", value: 11 }] }, { id: "relay", label: "Relay", observations: [{ label: "Session 1", value: 10 }, { label: "Session 2", value: 19, note: "A slow connected session." }, { label: "Disconnected", value: null, status: "failed", note: "Incomplete capture; no completion time." }] }, { id: "archive", label: "Archive Kit", observations: [{ label: "Prepared", value: 3 }, { label: "Recovery", value: null, status: "missing" }] }] }) +
      V.trajectory({ context: chartContext, title: "Handling effort across supplied rounds", xAxis: "Round", yAxis: "Handoff preparation", yUnit: "min", series: [{ id: "fieldbook", label: "Fieldbook", points: [{ label: "First export", x: 1, y: 12 }, { label: "Revised bundle", x: 2, y: null, note: "No handling record retained." }, { label: "Repeated export", x: 3, y: 8 }] }, { id: "relay", label: "Relay", points: [{ label: "First handoff", x: 1, y: 6 }, { label: "Repeated handoff", x: 2, y: 5 }, { label: "Follow-up", x: 3, y: 6 }] }] }),
    },
    { id: "tradeoffs", label: "Tradeoffs & scenarios", description: "Capture time and handoff effort favor different options under different conditions.", icon: "scenarios", body:
      V.scatterPlot(tradeoff) +
      V.scenarioExplorer(scenarios) +
      V.heatmap({ title: "Signed timing changes after preparation", rows: alternatives, columns: [{ id: "capture", label: "Capture step" }, { id: "export", label: "Export step" }], unit: "s", cells: [{ row: "fieldbook", column: "capture", value: -4 }, { row: "fieldbook", column: "export", value: 0 }, { row: "relay", column: "capture", value: 0 }, { row: "relay", column: "export", value: 2 }, { row: "archive", column: "capture", value: null }, { row: "archive", column: "export", value: null }], limitations: ["All cells use seconds; darker cells mean larger changes, not better outcomes."] }),
    },
    { id: "reliability", label: "Reliability", description: "Failures and evidence gaps keep their operating context.", icon: "compare", body:
      V.reliabilityProfile({ title: "Relay under different conditions", conditions: [{ id: "online", label: "Connected" }, { id: "offline", label: "Disconnected" }, { id: "large", label: "Large image set" }], behaviors: [{ id: "capture", label: "Notes retained" }, { id: "share", label: "Immediate sharing" }], observations: [{ condition: "online", behavior: "capture", value: "Ten notes retained", status: "supported" }, { condition: "online", behavior: "share", value: "Shared workspace available", status: "supported" }, { condition: "offline", behavior: "capture", value: "Eight of ten notes retained", status: "failed", evidence: source }, { condition: "offline", behavior: "share", value: "Connection unavailable", status: "failed" }], limitations: ["Unfilled large-image cells do not imply successful operation."] }) +
      V.failureTaxonomy({ title: "Why an attempt did not complete", categories: [{ label: "Connection required", definition: "A necessary save operation depends on the network.", alternative: "Relay", frequency: "Two notes in the supplied disconnected session", impact: "The capture requirement was not met.", conditions: "No network connection", cases: [{ label: "Disconnected capture", outcome: "Two notes remained pending.", evidence: source }] }] }) +
      V.coverageMatrix({ ...matrix, title: "The shape of the retained evidence", description: "Archive Kit has no observed original-record recovery result." }),
    },
    { id: "evidence", label: "Evidence & artifacts", description: "Move between claims, native records, and independent objections.", icon: "evidence", body:
      V.reportSection({ id: "handoff-flow", title: "How the next team receives the notes", body: V.mermaidDiagram({ id: "handoff-sequence", title: "Capture locally, then hand over the complete bundle", caption: "This sequence describes the export condition in the supplied pilot evidence; it does not establish recovery for longer trips.", source: "sequenceDiagram\n    participant Field as Field team\n    participant Local as Local bundle\n    participant Next as Next team\n    Field->>Local: Save ten notes and attachments offline\n    Local-->>Field: Retained records\n    Field->>Next: Export bundle and original context\n    Note over Next: Verify the received records before relying on them" }) }) +
      V.evidenceLineage(lineage) + V.nativeArtifactViewer({ ...artifacts, id: "native-records" }) +
      V.evidenceExcerpts({ title: "Native wording, side by side", items: [{ label: "Fieldbook record", text: "All ten notes are in the local bundle. Export is required before the next team can use them.", evidence: source }, { label: "Relay record", text: "Two notes are pending. Reconnect to finish saving.", status: "failed", evidence: source }, { label: "Archive Kit record", text: "Inputs were prepared before departure. Recovery was not exercised.", status: "uncertain" }] }) +
      V.disagreementMap({ title: "An objection can change the scope", topics: [{ topic: "Does a successful short session establish remote suitability?", positions: [{ contributor: "Reviewer Rowan", position: "The ten-note result supports the short pilot.", evidence: source }, { contributor: "Reviewer Ellis", position: "A full day with large photographs could behave differently.", note: "This objection does not invalidate the retained short-session observation." }], disposition: "Keep the pilot recommendation bounded. Longer remote use remains unresolved." }] }) +
      V.argumentMap({ ...lineage, title: "Reasons and objections around the pilot decision" }),
    },
    { id: "uncertainty", label: "Open questions", description: "Unknowns stay connected to the choices they can affect.", icon: "unknowns", body:
      V.uncertaintyObservatory(unknowns) + V.unknownsMap({ ...unknowns, title: "All open questions and their consequences" }) +
      V.confidenceProvenance({ title: "Why the pilot judgment is bounded", claims: [{ claim: "Fieldbook is suitable for the short disconnected pilot.", judgment: "Supported with an export condition.", basis: [{ dimension: "Direct observation", observation: "Ten notes and attachments were retained locally.", evidence: source }, { dimension: "Transfer", observation: "The next team needs the export bundle." }, { dimension: "Coverage", observation: "The record does not cover all-day use or large image sets." }] }] }),
    },
    { id: "record", label: "Decision record", description: "Preserve what was known, what changed, and what the work cost.", icon: "history", body:
      V.decisionHistory({ title: "A decision can become more precise", decisions: [{ label: "Initial review", when: "After the disconnected session", decision: "Fieldbook is suitable for a bounded pilot.", availableThen: "The ten-note save record and export requirement.", evidence: source }, { label: "Independent challenge", when: "After review", decision: "Retain the pilot recommendation; keep longer trips unresolved.", availableThen: "The same native record and a new coverage objection.", changesSince: "The longer-trip question is explicit.", supersedes: "Any unrestricted reading of remote suitability." }] }) +
      V.evidenceFreshness({ context: chartContext, title: "Observation and revision dates", events: [{ label: "First observation", source: "Capture record", date: "2026-01-15", event: "Short disconnected session", assessment: "Applies to the retained setup." }, { label: "Bundle revised", source: "Export revision", date: "2026-02-03", event: "Packaging changed", assessment: "Earlier packaging observations do not establish this revision." }, { label: "Recovery note", source: "Imported note", date: null, event: "Date not retained", assessment: "Chronology is unknown." }], note: "Dates are fictional study data." }) +
      V.effortTable({ title: "Execution and handling are different costs", items: [{ label: "Fieldbook", stage: "Capture", measure: "Elapsed time", value: 7, unit: "s", scope: "One prepared session", evidence: source }, { label: "Fieldbook", stage: "Handoff", measure: "Preparation", value: 12, unit: "min", scope: "First export" }, { label: "Relay", stage: "Handoff", measure: "Preparation", value: 6, unit: "min", scope: "Connected session" }, { label: "Archive Kit", stage: "Handoff", measure: "Preparation", value: null, unit: "min", scope: "No measurement retained" }] }) +
      V.renderExtension({ title: "A distinction worth preserving", purpose: "Local capture and a usable handoff answer different parts of the assignment.", blocks: [{ kind: "narrative", text: "A successful save and a usable handoff are separate outcomes. The exported bundle is part of Fieldbook's use, even though the capture itself finishes earlier." }, { kind: "table", input: { title: "Two consumer boundaries", columns: ["Boundary", "Required result"], rows: [[{ value: "Field capture" }, { value: "Original records retained without a connection" }], [{ value: "Next team" }, { value: "Usable export with the original records", status: "conditional", evidence: source }]] } }] }),
    },
  ];
  return V.evidenceWorkspace({
    id: "field-study", label: "Fictional field study", title: "Field notes beyond the signal",
    description: "Three ways to capture field notes. One short pilot. The choice depends on keeping the records and making the handoff work.", views,
    palette: "aurora", canvas: "textured", texture: "grain", intensity: "low", startView: "overview",
    brief: {
      question: "Which notebook should the team use for a short trip without a signal?",
      paragraphs: ["We compared Fieldbook, Relay and Archive Kit against the team's need to capture notes offline, retain the original records and hand the work to another team. The sections below connect each observation to those requirements."],
      facts: [
        { label: "The operating condition", text: "A short disconnected pilot with ten notes and attachments." },
        { label: "What matters", text: "Offline capture, original-record recovery and a usable handoff." },
        { label: "The evidence boundary", text: "The supplied sessions do not establish all-day use or large image sets.", status: "uncertain" },
      ],
      finding: [{ text: "Use Fieldbook for the bounded pilot", strong: true }, { text: ", and include its export bundle in the handoff. Different operating conditions can change that choice." }],
      evidence: source,
    },
    journeys: [
      { id: "decide", label: "Understand the choice", description: "The recommendation, the requirements, and when the choice changes.", viewIds: ["overview", "requirements", "tradeoffs"] },
      { id: "examine", label: "Examine the evidence", description: "Original records, measured behavior, and the questions still open.", viewIds: ["evidence", "measurements", "reliability", "uncertainty"] },
      { id: "trace", label: "Follow the reasoning", description: "Conditions, objections, and the decision record.", viewIds: ["requirements", "evidence", "record"] },
    ],
    notebook: { revision: "reader-experience-1", storageKey: "evidence-atelier:field-study:notebook", activityLimit: 80 },
    storageKey: "evidence-atelier:field-study:display",
    footer: '<aside id="synthetic-evidence"><h2>About this study</h2><p>All values, judgments, dates, names and artifacts here are synthetic demonstration inputs. They illustrate the visual library; they are not findings about real products or evidence of a tested workflow improvement.</p></aside>',
  });
}
