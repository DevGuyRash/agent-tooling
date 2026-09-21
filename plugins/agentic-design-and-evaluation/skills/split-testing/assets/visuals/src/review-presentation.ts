import { exactJson } from './exact-json';
import { ReviewAnchor } from './review-types';
/** Reader wording only. Identities and recorded evidence are never rewritten. */
export function anchorLabel(anchor: ReviewAnchor): string {
  return anchor.kind === 'item' ? anchor.label : anchor.kind === 'items' ? `${anchor.items.length} items · ${anchor.target.label}` : anchor.kind === 'text' ? 'Selected passage · ' + anchor.target.label : anchor.target.label;
}
export function anchorContext(anchor: ReviewAnchor): string { return anchor.target.path.join(' / '); }
export function anchorEvidence(anchor: ReviewAnchor): string {
  if (anchor.kind === 'text') return anchor.quote;
  if (anchor.kind === 'item') return `${anchor.label} (${anchor.itemId})\n${anchor.text}${anchor.values ? '\n' + exactJson(anchor.values) : ''}`;
  if (anchor.kind === 'items') return anchor.items.map(item => `${item.label} (${item.itemId})\n${item.text}${item.values ? '\n' + exactJson(item.values) : ''}`).join('\n\n');
  return anchor.target.excerpt;
}
export function readerDate(value: string, timeOnly = false): string {
  const date = new Date(value); if (!Number.isFinite(date.getTime())) return value;
  try { return new Intl.DateTimeFormat(undefined, timeOnly ? {hour:'numeric',minute:'2-digit'} : {month:'short',day:'numeric',year:'numeric',hour:'numeric',minute:'2-digit'}).format(date); } catch { return value; }
}
