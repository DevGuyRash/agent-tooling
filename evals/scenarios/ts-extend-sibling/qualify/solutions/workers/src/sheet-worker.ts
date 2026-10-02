// Parses one timesheet off the main thread: posts { entries } or { error: { kind, message } }.
import { parentPort, workerData } from 'node:worker_threads';
import { ReadError, TimesheetError, readTimesheet } from './timesheet.ts';

try {
  parentPort?.postMessage({ entries: readTimesheet(workerData as string) });
} catch (error) {
  const kind = error instanceof TimesheetError ? 'sheet' : error instanceof ReadError ? 'read' : 'other';
  parentPort?.postMessage({ error: { kind, message: (error as Error).message } });
}
