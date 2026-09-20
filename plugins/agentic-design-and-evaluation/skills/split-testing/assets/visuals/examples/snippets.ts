import * as V from "../src/index";

/** Two independent compositions using the same public fragments and controls. */
export function renderSnippets(): string {
  const compact = V.reportSurface({
    id: "compact-evidence", theme: "dark", palette: "graphite", canvas: "plain", spacing: "compact", sections: "solo",
    body: V.appearanceSettings({ id: "compact-display" }) + V.researchNotebook({ id:"compact-notebook",scopeId:"compact-evidence",revision:"illustrative-1" }) + V.sectionGroup({ body:
      V.annotatedTable({ id: "capture-observations", title: "Which records were retained?", columns: ["Observation", "Result", "Scope"], rows: [
        [{ value: "Attempt A" }, { value: 0, status: "supported" }, { value: "No records lost" }],
        [{ value: "Attempt B" }, { value: null, status: "missing" }, { value: "Recovery was not observed" }],
      ] }) + V.reportSection({ title: "Context behind the observations", body: '<p>No records were lost during attempt A. Recovery was not exercised during attempt B, so the missing result cannot establish success or failure.</p>' }) +
      V.mermaidDiagram({ id:"record-path",title:"A retained record can be handed over",caption:"Attempt B has no observed recovery result.",source:"flowchart LR\n  A[Original notes] --> B[Local record]\n  B --> C[Exported bundle]\n  C --> D[Receiving team]" }) +
      V.nativeArtifactViewer({ title: "Native record", artifacts: [{ label: "Capture log", mediaType: "text/plain", text: "attempt: A\nrecords lost: 0\nrecovery: not observed" }] }),
    }),
  });
  const open = V.reportSurface({
    id: "open-evidence", theme: "light", palette: "custom", customColors: { main: "#5266d4", secondary: "#087f8c", tertiary: "#d55b87" }, canvas: "textured", texture: "grid", intensity: "low", spacing: "comfortable", sections: "multiple",
    body: V.appearanceSettings({ id: "open-display" }) + V.researchNotebook({ id:"open-notebook",scopeId:"open-evidence",revision:"illustrative-1" }) + V.sectionGroup({ body:
      V.scatterPlot({ title: "Two costs, kept separate", xAxis: "Execution", xUnit: "s", yAxis: "Handling", yUnit: "min", points: [
        { id: "first", groupId: "first", group: "First", label: "First", x: 3, y: 12 }, { id: "second", groupId: "second", group: "Second", label: "Second", x: 8, y: 5 },
        { id: "third", groupId: "third", group: "Third", label: "Third", x: 6, y: null, note: "Handling cost is missing." },
      ] }) + V.storyPanel({ id: "cost-interpretation", title: "The faster run takes longer to hand over", lead: [{ text: "3 seconds to execute", tone: "accent", strong: true }, { text: " and " }, { text: "12 minutes to prepare the handoff", tone: "caution", strong: true }, { text: " describe different parts of the work." }], paragraphs: ["The second option takes 8 seconds to execute and 5 minutes to hand over. The third has no handling measurement. Choose according to the work that matters in this situation; a single combined score would need an agreed conversion."] }),
    }),
  });
  const compose = V.comparisonLanes({ title: "Read each set of evidence in its own context", lanes: [
    { id: "capture", label: "Record retention", body: compact },
    { id: "costs", label: "Execution and handoff", body: open },
  ] });
  return '<main class="av-report"><header style="max-width:1500px;margin:0 auto 1.5rem"><h1>Two questions. Different kinds of evidence.</h1><p>Record retention and handling effort need different readings. These fictional examples use independent surfaces in one composition.</p></header><div style="max-width:1500px;margin:auto">' + compose + '</div></main>';
}
