// Parses one timesheet in a process of its own: prints { entries } or { error: { kind, message } } as JSON.
import type { SheetResult } from './parallel.ts';
import { ReadError, TimesheetError, readTimesheet } from './timesheet.ts';

let result: SheetResult;
try {
  result = { entries: readTimesheet(process.argv[2]) };
} catch (error) {
  const kind = error instanceof TimesheetError ? 'sheet' : error instanceof ReadError ? 'read' : 'other';
  result = { error: { kind, message: (error as Error).message } };
}
process.stdout.write(JSON.stringify(result));
