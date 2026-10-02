// shelfwise holds: a branch's holds, oldest first.
import type { Hold } from '../holds.ts';

export function holdsReport(holds: Hold[], branch: string, status: string | undefined): string[] {
  const mine = holds
    .filter((h) => h.branch === branch && (status === undefined || h.status === status))
    .sort((a, b) => (a.placed < b.placed ? -1 : a.placed > b.placed ? 1 : a.id - b.id));
  const idWidth = Math.max(0, ...mine.map((h) => String(h.id).length + 1));
  return [
    `Holds for ${branch}: ${mine.length} ${mine.length === 1 ? 'hold' : 'holds'}`,
    ...mine.map((h) => `${h.placed}  ${`#${h.id}`.padEnd(idWidth)}  ${h.status.padEnd(9)}  ${h.title}`),
  ];
}
