import { documentId, escapeText as e } from "./core";
import { appearanceSettings, DisplayPreferences, surfaceAttributes } from "./preferences";

import { readingGuide, reportBrief, ReportBriefInput, inlineText } from "./story";
import { researchNotebook, ResearchNotebookInput } from "./notebook";

export type WorkspaceIcon = "overview" | "compare" | "plot" | "evidence" | "scenarios" | "unknowns" | "history";

export interface WorkspaceView {
  id: string;
  label: string;
  description?: string;
  icon?: WorkspaceIcon;
  /** Trusted author composition, such as the output of library renderers. */
  body: string;
}

export interface WorkspaceJourney { id: string; label: string; description?: string; viewIds: string[] }
export interface WorkspaceInput extends DisplayPreferences {
  /** Use a labelled region when embedding independent sibling reports in an app. */
  landmark?: "main" | "region";
  /** Authored question/context, visible before evidence sections and routes. */
  brief?: ReportBriefInput;
  /** Optional, author-defined reading paths through the supplied views. */
  journeys?: WorkspaceJourney[];
  startView?: string;
  notebook?: Omit<ResearchNotebookInput, "id" | "scopeId">;
  /** Include reusable display controls; true unless explicitly disabled. */
  settings?: boolean;
  /** Opt-in browser storage key for this report’s display preferences. */
  storageKey?: string;
  /** A unique document ID prefix, beginning with a letter. */
  id: string;
  title: string;
  description?: string;
  label?: string;
  views: WorkspaceView[];
  /** Trusted author composition. Evidence labels belong in escaped data fields. */
  footer?: string;
}

const icons: Record<WorkspaceIcon, string> = {
  overview: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  compare: '<path d="M4 5h16M4 12h16M4 19h16M9 3v18M16 3v18"/>',
  plot: '<path d="M4 3v17h17M7 15l4-6 4 3 5-7"/><circle cx="11" cy="9" r="1.5"/>',
  evidence: '<circle cx="6" cy="6" r="3"/><circle cx="18" cy="6" r="3"/><circle cx="12" cy="18" r="3"/><path d="M9 6h6M7.5 9l3 6M16.5 9l-3 6"/>',
  scenarios: '<path d="M5 3v18M12 3v18M19 3v18"/><rect x="2.5" y="7" width="5" height="4" rx="1"/><rect x="9.5" y="14" width="5" height="4" rx="1"/><rect x="16.5" y="5" width="5" height="4" rx="1"/>',
  unknowns: '<circle cx="12" cy="12" r="9"/><path d="M9 9a3 3 0 0 1 6 0c0 2-3 2-3 4M12 16v1"/>',
  history: '<path d="M4 8a9 9 0 1 1-1 7M4 3v5h5M12 6v6l4 2"/>',
};

function icon(value: WorkspaceIcon = "overview"): string {
  if (!Object.prototype.hasOwnProperty.call(icons, value)) throw new TypeError("Unknown workspace icon. Use overview, compare, plot, evidence, scenarios, unknowns, or history.");
  const path = icons[value];
  return `<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;
}

/** Optional report navigation; supplied views remain usable as an ordinary document without JavaScript. */
export function evidenceWorkspace(input: WorkspaceInput): string {
  const prefix = documentId(input.id, "Workspace ID"), seen = new Set<string>();
  if (input.landmark !== undefined && input.landmark !== "main" && input.landmark !== "region") throw new TypeError("Workspace landmark must be main or region.");
  const tag = input.landmark === "region" ? "section" : "main";
  if (typeof input.title !== "string" || !input.title.trim()) throw new TypeError("Supply a nonempty workspace title.");
  for (const view of input.views) {
    documentId(view.id, "View ID");
    if (seen.has(view.id)) throw new TypeError("Workspace view IDs must be unique.");
    seen.add(view.id);
    if (typeof view.label !== "string" || !view.label.trim()) throw new TypeError("Each workspace view needs a nonempty label.");
    if (typeof view.body !== "string") throw new TypeError("A view body must be trusted HTML produced by the report author.");
  }
  if (input.startView !== undefined && !seen.has(input.startView)) throw new TypeError("The starting view must be one of the supplied views.");
  const journeyIds = new Set<string>();
  for (const route of input.journeys || []) {
    documentId(route.id, "Journey ID");
    if (journeyIds.has(route.id)) throw new TypeError("Journey IDs must be unique.");
    journeyIds.add(route.id);
    if (!Array.isArray(route.viewIds) || !route.viewIds.length || new Set(route.viewIds).size !== route.viewIds.length || route.viewIds.some(view => !seen.has(view))) throw new TypeError("Each journey needs distinct steps referencing supplied views.");
  }
  const routes = input.journeys?.length ? readingGuide({ title: "Where would you like to start?", routes: input.journeys.map(route => ({ ...route, href: `#${prefix}--view-${route.viewIds[0]}` })) }) : "";
  const journeyControls = (input.journeys || []).map(route => `<nav class="av-reading-path" data-av-journey-id="${e(route.id)}" data-av-journey-label="${e(route.label)}" data-av-journey-steps="${e(JSON.stringify(route.viewIds))}" aria-label="${e(route.label)}" hidden><span class="av-path-context">${e(route.label)}<output data-av-path-position aria-live="polite"></output></span><button type="button" class="av-button" data-av-path-step="-1">Previous</button><button type="button" class="av-button" data-av-path-step="1">Next section</button><button type="button" class="av-button av-button-quiet" data-av-path-exit>Leave path</button></nav>`).join("");
  if (input.storageKey && input.storageKey === input.notebook?.storageKey) throw new TypeError("Display preferences and the notebook need different storage keys.");
  const notebook = input.notebook ? researchNotebook({ ...input.notebook, id: `${prefix}--notebook`, scopeId: prefix }) : "";
  const target = (view: WorkspaceView) => `${prefix}--view-${view.id}`;
  const heading = (view: WorkspaceView) => `${prefix}--heading-${view.id}`;
  const navigation = input.views.map(view => `<a class="av-nav-item" data-av-view="${e(view.id)}" href="#${e(target(view))}"><span class="av-nav-icon">${icon(view.icon)}</span><span><span class="av-nav-title">${e(view.label)}</span>${view.description ? `<span class="av-nav-description av-sr-only">${e(view.description)}</span>` : ""}</span></a>`).join("");
  const context = input.brief ? inlineText(input.brief.question) : e(input.title);
  const views = input.views.map(view => `<section class="av-workspace-panel" id="${e(target(view))}" data-av-panel="${e(view.id)}" aria-labelledby="${e(heading(view))}"><header class="av-panel-heading"><p class="av-view-question" data-av-view-question hidden><a href="#${e(prefix)}--title">${context}</a></p><h2 id="${e(heading(view))}">${e(view.label)}</h2>${view.description ? `<p>${e(view.description)}</p>` : ""}</header>${view.body}</section>`).join("");
  return `<${tag}${input.landmark === "region" ? ` role="region" aria-labelledby="${e(prefix)}--title"` : ""} id="${e(prefix)}" class="av-workspace av-report" data-av-view-total="${input.views.length}" data-av-workspace${input.startView ? ` data-av-start-view="${e(input.startView)}"` : ""} ${surfaceAttributes(input)}><a class="av-skip" href="#${e(prefix)}--content">Skip to evidence</a><header class="av-workspace-header"><div class="av-workspace-heading">${input.label ? `<p class="av-brand">${e(input.label)}</p>` : ""}<h1 class="av-workspace-title" id="${e(prefix)}--title">${e(input.title)}</h1>${input.description ? `<p class="av-workspace-intro">${e(input.description)}</p>` : ""}</div></header><div class="av-workspace-bar"><div class="av-search" data-av-script-only hidden><span class="av-search-icon" aria-hidden="true"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/></svg></span><label class="av-sr-only" for="${e(prefix)}--query">Find in this report</label><input id="${e(prefix)}--query" type="search" data-av-search placeholder="Find in this report" aria-describedby="${e(prefix)}--search-status"><button type="button" class="av-search-reset" data-av-search-reset aria-label="Clear search" hidden>×</button></div><div class="av-reading-mode" role="group" aria-label="Reading mode" data-av-script-only hidden><button type="button" class="av-button" data-av-show-single aria-label="Section view"><span class="av-mode-long">Section view</span><span class="av-mode-short" aria-hidden="true" data-av-review-ui>Section</span></button><button type="button" class="av-button" data-av-show-all aria-label="Full report"><span class="av-mode-long">Full report</span><span class="av-mode-short" aria-hidden="true" data-av-review-ui>All</span></button></div><div class="av-workspace-utilities">${input.settings === false ? "" : appearanceSettings({ id: `${prefix}--display` })}${notebook}</div><span class="av-view-count" data-av-view-count></span><div class="av-search-results" data-av-search-results role="region" aria-label="Search results" hidden></div><output class="av-search-status av-sr-only" id="${e(prefix)}--search-status" data-av-search-status aria-live="polite"></output></div>${input.brief ? reportBrief(input.brief) : ""}${routes}<div class="av-workspace-layout"><nav class="av-workspace-nav" aria-label="${e(input.title)} views">${navigation}</nav><div class="av-workspace-main" id="${e(prefix)}--content">${views || '<p class="av-empty">No views supplied.</p>'}${journeyControls}</div></div>${input.footer ? `<footer class="av-workspace-footer">${input.footer}</footer>` : ""}</${tag}>`;
}
