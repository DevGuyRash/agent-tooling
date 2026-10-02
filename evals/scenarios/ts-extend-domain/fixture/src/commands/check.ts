// shelfwise check: every record of the export that is not a good hold, and repeated hold ids.
import type { Record } from '../csv.ts';
import { problem } from '../holds.ts';

export function checkReport(records: Record[]): { lines: string[]; problems: number } {
  const lines: string[] = [];
  const seen = new Map<string, number>();
  for (const { line, fields } of records) {
    const wrong = problem(fields);
    if (wrong) {
      lines.push(`line ${line}: ${wrong}`);
      continue;
    }
    const first = seen.get(fields[0]);
    if (first !== undefined) lines.push(`line ${line}: hold #${fields[0]} already on line ${first}`);
    else seen.set(fields[0], line);
  }
  const problems = lines.length;
  lines.push(`${records.length} ${records.length === 1 ? 'hold' : 'holds'}, ${problems} ${problems === 1 ? 'problem' : 'problems'}`);
  return { lines, problems };
}
