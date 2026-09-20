export type ReviewAnchor =
  | { kind: 'section' | 'figure'; target: ReviewTarget }
  | { kind: 'text'; target: ReviewTarget; quote: string; prefix: string; suffix: string; start: number; end: number }
  | { kind: 'item'; target: ReviewTarget; itemId: string; label: string; text: string; values?: Record<string,string|number|null> };
export interface ReviewTarget { reportId: string; revision: string; id: string; label: string; path: string[]; fingerprint: string; ambiguous?: boolean; sources?: {label:string;href:string}[]; excerpt: string }
