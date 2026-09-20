import { escapeText as e } from './core';
import { AnnotationVersion } from './review-state';
import { ReaderNotebook } from './reader-state';
import { ReviewAnchor, TargetRegistry } from './review-targets';
interface Recipe { kind: 'agentic-report-recipe'; version: 1; lang: string; title: string; csp: string; body: string; styles: string[]; data: string[]; scripts: string[] }
interface OriginalReport { recipe: Recipe; styles: string[]; data: string[]; scripts: string[] }
const originals = new WeakMap<Document, OriginalReport>();
const json = (value: unknown) => JSON.stringify(value).replace(/</g,'\\u003c').replace(/>/g,'\\u003e').replace(/&/g,'\\u0026').replace(/\u2028/g,'\\u2028').replace(/\u2029/g,'\\u2029');
export function retainReportRecipe(document: Document): void {
  if(originals.has(document))return;
  const element=document.getElementById('av-report-recipe');if(!element)return;
  const recipe=JSON.parse(element.textContent||'null') as Recipe;
  if(recipe?.kind!=='agentic-report-recipe'||recipe.version!==1||![recipe.lang,recipe.title,recipe.csp,recipe.body].every(value=>typeof value==='string')||![recipe.styles,recipe.data,recipe.scripts].every(values=>Array.isArray(values)&&values.every(value=>typeof value==='string')))throw new Error('The retained report recipe is unavailable or unsupported.');
  const styles=recipe.styles.map(id=>{const node=document.getElementById(id),href=node?.getAttribute('href');if(node?.tagName.toLowerCase()!=='link'||!href?.startsWith('data:text/css'))throw new Error('An original report stylesheet is missing.');return `<link id="${e(id)}" rel="stylesheet" href="${e(href)}">`;});
  const scripts=recipe.scripts.map(id=>{const node=document.getElementById(id),src=node?.getAttribute('src');if(node?.tagName.toLowerCase()!=='script'||!src?.startsWith('data:text/javascript'))throw new Error('An original report script is missing.');return `<script id="${e(id)}" src="${e(src)}"></script>`;});
  const data=recipe.data.map(id=>{const node=document.getElementById(id);if(node?.getAttribute('type')!=='application/json')throw new Error('Original report data is missing.');const raw=node.textContent||'';JSON.parse(raw);return `<script type="application/json" id="${e(id)}">${raw.replace(/</g,'\\u003c')}</script>`;});
  originals.set(document,{recipe,styles,scripts,data});
}
export interface ReviewSeed { kind: 'agentic-report-review'; version: 1; reports: Record<string, ReaderNotebook>; exportedAt: string }
export function readReviewSeed(document: Document): ReviewSeed | null {
  const node=document.getElementById('av-review-seed');if(!node)return null;const value=JSON.parse(node.textContent||'null');
  if(value?.kind!=='agentic-report-review'||value.version!==1||!value.reports||typeof value.reports!=='object'||Array.isArray(value.reports))throw new Error('The embedded review copy has an unsupported format.');return value;
}
export function annotatedReport(document: Document, reports: Record<string, ReaderNotebook>, at: string): string {
  retainReportRecipe(document);const original=originals.get(document);if(!original)throw new Error('This report has no assembly recipe. Export the notebook and handoff, or reassemble the report with the current packager.');
  const{recipe,styles,data,scripts}=original,seed:ReviewSeed={kind:'agentic-report-review',version:1,reports,exportedAt:at};
  return ['<!doctype html>',`<html lang="${e(recipe.lang)}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">`,`<meta http-equiv="Content-Security-Policy" content="${e(recipe.csp)}"><title>${e(recipe.title)}</title>`,...styles,'</head><body>',recipe.body,...data,`<script type="application/json" id="av-report-recipe">${json(recipe)}</script>`,`<script type="application/json" id="av-review-seed">${json(seed)}</script>`,...scripts,'</body></html>',''].join('\n');
}
function anchorText(anchor: ReviewAnchor): string {
  const lines=[`${anchor.target.path.concat(anchor.target.label).join(' / ')} (#${anchor.target.id})`,`Original report: ${anchor.target.reportId}; original revision: ${anchor.target.revision}`,`Target fingerprint: ${anchor.target.fingerprint}`];
  if(anchor.kind==='text')lines.push('Quoted passage:',anchor.quote,'Surrounding text:',anchor.prefix+' ['+anchor.quote+'] '+anchor.suffix);
  else if(anchor.kind==='item')lines.push(`Item: ${anchor.label} (${anchor.itemId})`,anchor.text,anchor.values?JSON.stringify(anchor.values):'');
  else lines.push(anchor.target.excerpt);
  if(anchor.target.sources?.length)lines.push('Source references:',...anchor.target.sources.map(source=>`${source.label}: ${source.href}`));
  return lines.filter(Boolean).join('\n');
}
/** Literal blocks prevent evidence/feedback from becoming headings, links or HTML.
 * Pick a fence longer than anything in the content; do not alter its text. */
function literal(value: string): string {
  const longest = (value.match(/`+/g) || []).reduce((length, run) => Math.max(length, run.length), 0);
  const fence = '`'.repeat(Math.max(3, longest + 1));
  return fence + 'text\n' + value + (value.endsWith('\n') ? '' : '\n') + fence;
}
export function reviewHandoff(notebook: ReaderNotebook, registry: TargetRegistry, question: string, sourceTitle: string): string {
  const lines = ['# Reader feedback', literal(sourceTitle), literal(`Report: ${notebook.state.reportId}\nRevision: ${notebook.state.revision}`),
    '## Original question and context', question ? literal(question) : 'No separate opening question was supplied.',
    'Reader annotations are feedback, not changes to the findings. Use the original report and requirements to interpret them.'];
  const counts = new Map<string, number>();
  for (const version of notebook.noteVersions) counts.set(version.targetId, (counts.get(version.targetId) || 0) + 1);
  for (const version of notebook.noteVersions) {
    const target = registry.targets.get(version.targetId)?.target;
    lines.push('## Note' + ((counts.get(version.targetId) || 0) > 1 ? ' — competing version' : ''),
      literal(target?.label || version.targetId), literal(version.text === null ? '[Removed in this version]' : version.text),
      literal('Target ID: ' + version.targetId), 'This note did not record its original evidence fingerprint. The current label is an orientation aid, not confirmation of an unchanged attachment.');
  }
  const groups = new Map<string, AnnotationVersion[]>();
  for (const version of notebook.review?.versions || []) { const list = groups.get(version.annotationId) || []; list.push(version); groups.set(version.annotationId, list); }
  for (const [id, versions] of groups) for (const version of versions) {
    const resolution = registry.resolve(version.anchor);
    const competing = versions.filter(other => other.draft === version.draft).length > 1;
    lines.push(`## ${version.draft ? 'Draft' : 'Annotation'}${competing ? ' — competing version' : ''}`,
      literal(`Annotation: ${id}\nRecorded: ${version.at}\nAttachment: ${resolution.status}. ${resolution.message}`),
      '### Original evidence', literal(anchorText(version.anchor)), '### Reader note',
      literal(version.text === null ? '[Removed in this version]' : version.text || '[Empty draft]'));
  }
  const bookmarks = [...notebook.state.bookmarks.map(id => registry.targets.get(id)?.target).filter(Boolean).map(target => anchorText({ kind: 'section', target: target! })), ...(notebook.review?.bookmarks || []).map(anchorText)];
  if (bookmarks.length) lines.push('## Bookmarks', ...bookmarks.map(literal));
  if (notebook.originals.length) lines.push('Original notebook records are retained in the structured export for recovery.');
  return lines.join('\n\n') + '\n';
}
