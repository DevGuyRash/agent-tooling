/** Line and word diffs for comparing two texts, such as two arms' instructions.
 * Myers' O(ND) shortest edit script over lines, after the common head and tail
 * are set aside. Pure functions over strings: no DOM, no markup. */

/** One line of a diff. `a` and `b` are 1-based line numbers in the first and
 * second text; an added line has no `a`, a removed line no `b`. */
export interface DiffLine { op: "same" | "add" | "del"; text: string; a?: number; b?: number }

/** Lines of a text. Any line ending (\n, \r\n, \r) ends a line, and one final
 * line ending does not start an empty line, so "a\n" and "a" both have one line. */
export function splitLines(text: string): string[] {
  const value = typeof text === "string" ? text : "";
  if (!value) return [];
  const lines = value.split(/\r\n|\r|\n/);
  if (lines.length > 1 && lines[lines.length - 1] === "") lines.pop();
  return lines;
}

type Step = ["same" | "add" | "del", number, number];

/** The shortest edit script from a to b, or null when it needs more than
 * `budget` insertions and deletions. Steps index into a (del, same) and b (add, same). */
function myers<T>(a: readonly T[], b: readonly T[], budget: number): Step[] | null {
  const n = a.length, m = b.length, max = n + m, offset = max + 1;
  const v = new Int32Array(2 * max + 3);
  const trace: Int32Array[] = [];
  for (let d = 0; d <= Math.min(max, budget); d++) {
    trace.push(v.slice(offset - d - 1, offset + d + 2));
    for (let k = -d; k <= d; k += 2) {
      let x = k === -d || (k !== d && v[offset + k - 1] < v[offset + k + 1]) ? v[offset + k + 1] : v[offset + k - 1] + 1;
      let y = x - k;
      while (x < n && y < m && a[x] === b[y]) { x++; y++; }
      v[offset + k] = x;
      if (x >= n && y >= m) return backtrack(trace, n, m);
    }
  }
  return null;
}

function backtrack(trace: Int32Array[], n: number, m: number): Step[] {
  const steps: Step[] = [];
  let x = n, y = m;
  for (let d = trace.length - 1; d >= 0; d--) {
    const at = (k: number) => trace[d][k + d + 1];
    const k = x - y;
    const prevK = k === -d || (k !== d && at(k - 1) < at(k + 1)) ? k + 1 : k - 1;
    const prevX = at(prevK), prevY = prevX - prevK;
    while (x > prevX && y > prevY) { x--; y--; steps.push(["same", x, y]); }
    if (d > 0) { if (x === prevX) { y--; steps.push(["add", x, y]); } else { x--; steps.push(["del", x, y]); } }
    x = prevX; y = prevY;
  }
  return steps.reverse();
}

/** Edits beyond which a line diff reports the differing middle as one replaced
 * block: two texts that share almost nothing gain nothing from a finer script. */
const LINE_BUDGET = 2000;

/** A line diff from `before` to `after`. Within each changed stretch, removed
 * lines come before added ones, so a reader sees what went and then what came. */
export function lineDiff(before: string, after: string): DiffLine[] {
  const a = splitLines(before), b = splitLines(after);
  let head = 0;
  while (head < a.length && head < b.length && a[head] === b[head]) head++;
  let tail = 0;
  while (tail < a.length - head && tail < b.length - head && a[a.length - 1 - tail] === b[b.length - 1 - tail]) tail++;
  const midA = a.slice(head, a.length - tail), midB = b.slice(head, b.length - tail);
  const out: DiffLine[] = [];
  for (let i = 0; i < head; i++) out.push({ op: "same", text: a[i], a: i + 1, b: i + 1 });
  const steps = myers(midA, midB, LINE_BUDGET)
    ?? [...midA.map((_, i): Step => ["del", i, 0]), ...midB.map((_, j): Step => ["add", 0, j])];
  let dels: DiffLine[] = [], adds: DiffLine[] = [];
  const flush = () => { out.push(...dels, ...adds); dels = []; adds = []; };
  for (const [op, i, j] of steps) {
    if (op === "same") { flush(); out.push({ op, text: midA[i], a: head + i + 1, b: head + j + 1 }); }
    else if (op === "del") dels.push({ op, text: midA[i], a: head + i + 1 });
    else adds.push({ op, text: midB[j], b: head + j + 1 });
  }
  flush();
  for (let i = tail; i > 0; i--) out.push({ op: "same", text: a[a.length - i], a: a.length - i + 1, b: b.length - i + 1 });
  return out;
}

export interface DiffStats { added: number; removed: number; same: number }
export function diffStats(lines: readonly DiffLine[]): DiffStats {
  const s = { added: 0, removed: 0, same: 0 };
  for (const l of lines) { if (l.op === "add") s.added++; else if (l.op === "del") s.removed++; else s.same++; }
  return s;
}

/** A diff cut into stretches to show and unchanged stretches to fold: `context`
 * unchanged lines stay beside each change, and a fold always hides at least
 * `minFold` lines, since folding fewer saves the reader nothing. */
export interface DiffRun { fold: boolean; lines: DiffLine[] }
export function diffRuns(lines: readonly DiffLine[], context = 3, minFold = 4): DiffRun[] {
  const runs: DiffRun[] = [];
  const show = (part: DiffLine[]) => { if (!part.length) return; const last = runs[runs.length - 1]; if (last && !last.fold) last.lines.push(...part); else runs.push({ fold: false, lines: part }); };
  let i = 0;
  while (i < lines.length) {
    let j = i;
    const same = lines[i].op === "same";
    while (j < lines.length && (lines[j].op === "same") === same) j++;
    const part = lines.slice(i, j);
    if (!same) show(part);
    else {
      const first = i === 0, last = j === lines.length;
      const keepHead = first ? 0 : context, keepTail = last ? 0 : context;
      if (part.length - keepHead - keepTail >= minFold) {
        show(part.slice(0, keepHead));
        runs.push({ fold: true, lines: part.slice(keepHead, part.length - keepTail) });
        show(part.slice(part.length - keepTail));
      } else show(part);
    }
    i = j;
  }
  return runs;
}

/** A piece of a changed line; `changed` marks the words that differ from its partner line. */
export interface WordPiece { text: string; changed: boolean }

const TOKEN = /\s+|[\p{L}\p{N}_]+|[^\s\p{L}\p{N}_]/gu;
const WORD_BUDGET = 400;
const LONGEST_LINE = 4000;

/** Word-level difference between a removed line and the added line that
 * replaced it, or null when the lines share too little for marks to help. */
export function wordDiff(before: string, after: string): { before: WordPiece[]; after: WordPiece[] } | null {
  if (before.length > LONGEST_LINE || after.length > LONGEST_LINE) return null;
  const a = before.match(TOKEN) || [], b = after.match(TOKEN) || [];
  const steps = myers(a, b, WORD_BUDGET);
  if (!steps) return null;
  let shared = 0;
  for (const [op, i] of steps) if (op === "same" && /\S/.test(a[i])) shared += a[i].length;
  const visible = (s: string) => s.replace(/\s+/g, "").length;
  if (shared < 0.4 * Math.max(visible(before), visible(after), 1)) return null;
  const pieces = (side: "before" | "after"): WordPiece[] => {
    const out: WordPiece[] = [];
    for (const [op, i, j] of steps) {
      if (side === "before" ? op === "add" : op === "del") continue;
      const text = side === "before" ? a[i] : b[j], changed = op !== "same";
      const prev = out[out.length - 1];
      // Whitespace between two changed words joins the change, so a phrase reads as one mark.
      if (prev && prev.changed === changed) prev.text += text; else out.push({ text, changed });
    }
    for (let k = 1; k < out.length - 1; k++) {
      if (!out[k].changed && /^\s+$/.test(out[k].text) && out[k - 1].changed && out[k + 1].changed) {
        out[k - 1].text += out[k].text + out[k + 1].text;
        out.splice(k, 2); k--;
      }
    }
    return out;
  };
  return { before: pieces("before"), after: pieces("after") };
}
