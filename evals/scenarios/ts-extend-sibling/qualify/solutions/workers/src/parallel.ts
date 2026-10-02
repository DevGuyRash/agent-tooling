// Reads several timesheets at once, one worker thread per file (at most four at a time), and hands back the
// results in the order the files were given so the first mistake reported is the first in that order.
import { Worker } from 'node:worker_threads';
import type { Entry } from './timesheet.ts';

export type SheetResult = { entries: Entry[] } | { error: { kind: 'sheet' | 'read' | 'other'; message: string } };

function one(file: string): Promise<SheetResult> {
  return new Promise((resolve, reject) => {
    const w = new Worker(new URL('./sheet-worker.ts', import.meta.url), { workerData: file });
    w.once('message', (m: SheetResult) => resolve(m));
    w.once('error', reject);
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
