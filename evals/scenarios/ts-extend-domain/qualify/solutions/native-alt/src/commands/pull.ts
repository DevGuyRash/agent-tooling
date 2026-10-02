// shelfwise pull (docs/pull.md).
import { BadCallNumber, CallNumber, compareKeys } from '../catalog/call-number.ts';
import type { Hold } from '../holds.ts';

interface Pulled {
  hold: Hold;
  callNumber: CallNumber;
}

export function pullReport(holds: Hold[], branch: string): { text: string; status: number } {
  const waiting = holds.filter((h) => h.status === 'waiting' && h.branch === branch);
  const pulled: Pulled[] = [];
  const unfixed = new Map<number, string>();
  for (const hold of waiting) {
    try {
      pulled.push({ hold, callNumber: CallNumber.parse(hold.callNumber) });
    } catch (e) {
      if (e instanceof BadCallNumber) unfixed.set(hold.id, `  #${hold.id}  "${hold.callNumber}": ${e.message}`);
      else throw e;
    }
  }
  pulled.sort((a, b) => compareKeys(a.callNumber.key, b.callNumber.key) || a.hold.id - b.hold.id);
  const texts = pulled.map((p) => p.callNumber.toString());
  const width = texts.reduce((w, t) => Math.max(w, t.length), 0);
  const sections = new Map<string, string[]>();
  pulled.forEach((p, i) => {
    const lines = sections.get(p.callNumber.heading) ?? [];
    lines.push(`  ${texts[i].padEnd(width)}  ${p.hold.title}  #${p.hold.id}`);
    sections.set(p.callNumber.heading, lines);
  });
  let text = `Pull list for ${branch}: ${waiting.length} hold${waiting.length === 1 ? '' : 's'}\n`;
  for (const [heading, lines] of sections) text += `\n${heading}\n${lines.join('\n')}\n`;
  if (unfixed.size) {
    const ids = [...unfixed.keys()].sort((a, b) => a - b);
    text += `\nNot pulled, call number needs fixing:\n${ids.map((id) => unfixed.get(id)).join('\n')}\n`;
  }
  return { text, status: unfixed.size ? 1 : 0 };
}
