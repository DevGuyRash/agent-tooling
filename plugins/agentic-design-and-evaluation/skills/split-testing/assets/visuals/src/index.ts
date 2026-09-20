export * from "./model";
export * from "./atelier";
export { appearanceSettings, reportSurface, reportSection, sectionGroup } from "./preferences";
export type { DisplayPreferences, ThemeColors, ThemeChoice, SpacingChoice, SectionChoice, PaletteChoice, CanvasChoice, TextureChoice, IntensityChoice, SurfaceInput } from "./preferences";
export { enhanceVisuals } from "./interaction";
export type { EnhancementCleanup } from "./interaction";
export { comparisonJourney, uncertaintyObservatory } from "./explorers";
export { escapeText } from "./core";
export { annotatedTable, comparisonMatrix, coverageMatrix, constraintSatisfaction, conditionalRecommendations, heatmap } from "./structured";
export { pairedComparison, intervalPlot, distribution, trajectory, scatterPlot } from "./quantitative";
export { evidenceExcerpts, disagreementMap, uncertaintyPanel, evidenceLineage, failureTaxonomy, scenarioExplorer, nativeArtifactViewer, effortTable, renderExtension } from "./qualitative";
export { evidenceFreshness, unknownsMap, confidenceProvenance, reliabilityProfile, constraintMap, decisionHistory, argumentMap } from "./landscape";
export { inlineText, reportBrief, storyPanel, comparisonLanes, readingGuide } from "./story";
export type { ReportBriefInput, InlineText, InlineTone, InlineSegment, StoryInput, StoryTakeaway, ComparisonLane, ComparisonLanesInput, ReadingRoute, ReadingGuideInput } from "./story";
export { researchNotebook } from "./notebook";
export type { ResearchNotebookInput } from "./notebook";
export { createChartContext } from "./categories";
export type { ChartContext, CategoryDefinition, CategoryStyle, MarkerShape } from "./categories";
export { browserTextMeasure } from "./text-layout";

export { visualFigure, mermaidDiagram, registerVisualAdapter } from "./figures";
export type { VisualFigureInput, MermaidDiagramInput, VisualAdapter, FigureBounds, FigureSource, FigureItem } from "./figures";

export type { ReviewAnchor, ReviewTarget, ResolvedAnchor } from "./review-targets";
