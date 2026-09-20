import { Annotation, Meta, Named, Status } from "./model";
import { annotation, card, documentId, escapeText as e, labelMarkup, named, namedLabels, status } from "./core";

export type InlineTone = "plain" | "accent" | "positive" | "caution" | "negative" | "muted";
export interface InlineSegment { text: string | number; tone?: InlineTone; strong?: boolean }
export type InlineText = string | readonly InlineSegment[];

export interface StoryTakeaway extends Annotation { label: string; text: InlineText; status?: Status }
export interface StoryInput extends Meta {
  lead?: InlineText;
  paragraphs?: InlineText[];
  takeaways?: StoryTakeaway[];
}

export interface ComparisonLane extends Named {
  /** Trusted author composition, such as the output of library renderers. */
  body: string;
}
export interface ComparisonLanesInput {
  title?: string;
  description?: string;
  lanes: ComparisonLane[];
  sectionMode?: "multiple" | "solo";
}

export interface ReadingRoute { id: string; label: string; description?: string; href: string }
export interface ReadingGuideInput { title?: string; description?: string; routes: ReadingRoute[] }

const tones: InlineTone[] = ["plain", "accent", "positive", "caution", "negative", "muted"];

/** Emphasis and color express author-supplied meaning; all segment content remains text. */
export function inlineText(value: InlineText): string {
  if (typeof value === "string") return e(value);
  if (!Array.isArray(value)) throw new TypeError("Inline text must be a string or an array of text segments.");
  return value.map((segment: InlineSegment) => {
    if (!segment || typeof segment !== "object" || Array.isArray(segment)) throw new TypeError("Each inline segment must supply text, with optional tone and strong emphasis.");
    if (segment.tone !== undefined && !tones.includes(segment.tone)) throw new TypeError("Unknown inline tone. Use plain, accent, positive, caution, negative, or muted.");
    if (segment.strong !== undefined && typeof segment.strong !== "boolean") throw new TypeError("Inline strong emphasis must be true or false.");
    const text = e(segment.text), emphasis = segment.strong ? `<strong>${text}</strong>` : text;
    return segment.tone === undefined ? emphasis : `<span class="av-tone-${segment.tone}">${emphasis}</span>`;
  }).join("");
}

/** Compose only the supplied explanation and findings, retaining the shared evidence frame. */
export function storyPanel(input: StoryInput): string {
  if (input.paragraphs !== undefined && !Array.isArray(input.paragraphs)) throw new TypeError("Story paragraphs must be an array of inline text.");
  if (input.takeaways !== undefined && !Array.isArray(input.takeaways)) throw new TypeError("Story takeaways must be an array of authored findings.");
  const lead = input.lead === undefined ? "" : `<p class="av-story-lead">${inlineText(input.lead)}</p>`;
  const paragraphs = (input.paragraphs || []).map(paragraph => `<p class="av-story-paragraph">${inlineText(paragraph)}</p>`).join("");
  const takeaways = input.takeaways?.length ? `<ul class="av-story-takeaways">${input.takeaways.map(item => `<li class="av-story-takeaway"><header><h3>${e(item.label)}</h3>${status(item.status)}</header><p>${inlineText(item.text)}</p>${annotation(item)}</li>`).join("")}</ul>` : "";
  return card(input, `<div class="av-story">${lead}${paragraphs}${takeaways}</div>`, "interpretation");
}

/** Each lane owns its disclosure group and flow; position implies no analytical equivalence. */
export function comparisonLanes(input: ComparisonLanesInput): string {
  if (!Array.isArray(input.lanes)) throw new TypeError("Comparison lanes must be an array of named author compositions.");
  if (input.sectionMode !== undefined && input.sectionMode !== "multiple" && input.sectionMode !== "solo") throw new TypeError("Unknown section mode. Use multiple or solo.");
  for (const lane of input.lanes) {
    if (!lane || typeof lane !== "object") throw new TypeError("Each comparison lane must supply an ID, label and trusted author body.");
    if (typeof lane.label !== "string") throw new TypeError("Each comparison lane needs a text label.");
    if (typeof lane.body !== "string") throw new TypeError("A lane body must be trusted HTML produced by the report author.");
  }
  named(input.lanes, "Comparison lanes");
  const labels = namedLabels(input.lanes);
  const heading = `${input.title === undefined ? "" : `<h2>${e(input.title)}</h2>`}${input.description === undefined ? "" : `<p>${e(input.description)}</p>`}`;
  const mode = input.sectionMode === undefined ? "" : ` data-av-section-mode="${input.sectionMode}"`;
  const lanes = input.lanes.map(lane => `<section class="av-lane" data-av-lane="${e(lane.id)}" data-av-section-group${mode}><header class="av-lane-heading"><h3>${labelMarkup(labels.get(lane.id)!)}</h3>${annotation(lane)}</header>${lane.body}</section>`).join("");
  return `<section class="av-comparison-lanes">${heading ? `<header>${heading}</header>` : ""}${lanes}</section>`;
}

/** Native same-document choices remain useful without enhancement; destinations are author supplied. */
export function readingGuide(input: ReadingGuideInput): string {
  if (!Array.isArray(input.routes)) throw new TypeError("Reading routes must be an array of authored choices.");
  const ids = new Set<string>(), labels = new Set<string>();
  for (const route of input.routes) {
    if (!route || typeof route !== "object") throw new TypeError("Each reading route must supply an ID, label and same-document fragment link.");
    if (typeof route.id !== "string" || !route.id.trim() || ids.has(route.id)) throw new TypeError("Reading route IDs must be nonempty and unique.");
    if (typeof route.label !== "string" || !route.label.trim()) throw new TypeError("Reading route labels must be nonempty and unique.");
    const label = route.label.replace(/[ \t\n\r\f]+/g, " ").trim();
    if (labels.has(label)) throw new TypeError("Reading route labels must be nonempty and unique.");
    if (typeof route.href !== "string" || !/^#[A-Za-z][A-Za-z0-9_.:-]*$/.test(route.href) || route.href !== route.href.trim()) throw new TypeError("Reading route links must be same-document fragments beginning with # and a letter, followed by letters, numbers, underscores, periods, colons or hyphens.");
    ids.add(route.id);
    labels.add(label);
  }
  const title = input.title === undefined ? "" : `<h2>${e(input.title)}</h2>`;
  const description = input.description === undefined ? "" : `<p>${e(input.description)}</p>`;
  const routes = input.routes.map(route => `<li><a class="av-route-choice" data-av-start-journey="${e(route.id)}" href="${e(route.href)}"><span>${e(route.label)}</span>${route.description === undefined ? "" : `<span class="av-route-description">${e(route.description)}</span>`}</a></li>`).join("");
  return `<nav class="av-reading-guide" aria-label="${e(input.title || "Reading guide")}">${title}${description}<ul>${routes}</ul></nav>`;
}

export interface ReportBriefInput extends Annotation {
  question: InlineText;
  id?: string;
  paragraphs?: InlineText[];
  facts?: StoryTakeaway[];
  finding?: InlineText;
  findingLabel?: string;
  /** Optional trusted author composition after the supplied opening text. */
  body?: string;
}

/** A visible opening question and as much authored grounding as the reader needs. */
export function reportBrief(input: ReportBriefInput): string {
  const question = inlineText(input.question);
  if (!question.trim() || (Array.isArray(input.question) && !input.question.some(segment => String(segment.text).trim()))) throw new TypeError("An opening brief needs the actual question or task.");
  if (input.body !== undefined && typeof input.body !== "string") throw new TypeError("The opening body must be trusted author-owned HTML.");
  const paragraphs = (input.paragraphs || []).map(text => `<p class="av-brief-paragraph">${inlineText(text)}</p>`).join("");
  const facts = input.facts?.length ? `<dl class="av-brief-facts">${input.facts.map(fact => `<div><dt>${e(fact.label)}</dt><dd>${inlineText(fact.text)}${status(fact.status)}${annotation(fact)}</dd></div>`).join("")}</dl>` : "";
  const finding = input.finding === undefined ? "" : `<div class="av-brief-finding"><h3>${e(input.findingLabel || "What the evidence supports")}</h3><p>${inlineText(input.finding)}</p></div>`;
  return `<section class="av-report-brief"${input.id !== undefined ? ` id="${e(documentId(input.id))}"` : ""}><h2>${question}</h2>${paragraphs}${facts}${finding}${input.body || ""}${annotation(input)}</section>`;
}
