// Reads several timesheets at once, each in a Node process of its own (at most four at a time), and hands back the
// results in the order the files were given so the first mistake reported is the first in that order.
import { execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import type { Entry } from './timesheet.ts';

export type SheetResult = { entries: Entry[] } | { error: { kind: 'sheet' | 'read' | 'other'; message: string } };

const CHILD = fileURLToPath(new URL('./sheet-child.ts', import.meta.url));

function one(file: string): Promise<SheetResult> {
  return new Promise((resolve, reject) => {
    execFile(process.execPath, [CHILD, file], { maxBuffer: 1 << 28 }, (error, stdout) => {
      if (error) reject(error);
      else resolve(JSON.parse(stdout) as SheetResult);
    });
  });
}

export async function readAll(files: string[], limit = 4): Promise<SheetResult[]> {
  const out: SheetResult[] = new Array(files.length);
  let next = 0;
  const lane = async () => {
    while (next < files.length) {
      const i = next++;
      out[i] = await one(files[i]);
    }
  };
  await Promise.all(Array.from({ length: Math.min(limit, files.length) }, lane));
  return out;
}
