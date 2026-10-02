// shelfwise pull: the morning pull list (docs/pull.md), a branch's waiting holds in shelf order.
import { CallNumberError, compare, format, parse, section, type CallNumber } from '../callnumber.ts';
import type { Hold } from '../holds.ts';

export function pullList(holds: Hold[], branch: string): { lines: string[]; bad: number } {
  const waiting = holds.filter((h) => h.branch === branch && h.status === 'waiting');
  const good: { hold: Hold; cn: CallNumber; text: string }[] = [];
  const bad: { hold: Hold; reason: string }[] = [];
  for (const hold of waiting) {
    try {
      const cn = parse(hold.callNumber);
      good.push({ hold, cn, text: format(cn) });
    } catch (error) {
      if (!(error instanceof CallNumberError)) throw error;
      bad.push({ hold, reason: error.message });
    }
  }
  good.sort((a, b) => compare(a.cn, b.cn) || a.hold.id - b.hold.id);
  bad.sort((a, b) => a.hold.id - b.hold.id);
  const lines = [`Pull list for ${branch}: ${waiting.length} ${waiting.length === 1 ? 'hold' : 'holds'}`];
  const width = Math.max(0, ...good.map((g) => g.text.length));
  let current: string | undefined;
  for (const { hold, cn, text } of good) {
    const heading = section(cn);
    if (heading !== current) {
      lines.push('', heading);
      current = heading;
    }
    lines.push(`  ${text.padEnd(width)}  ${hold.title}  #${hold.id}`);
  }
  if (bad.length) {
    lines.push('', 'Not pulled, call number needs fixing:');
    for (const { hold, reason } of bad) lines.push(`  #${hold.id}  "${hold.callNumber}": ${reason}`);
  }
  return { lines, bad: bad.length };
}
