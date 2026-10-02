// The holds export from the library system: one hold per line, with a header.
//
//   hold_id,branch,placed,title,call_number,status
//
// hold_id is a positive whole number, placed a date (YYYY-MM-DD), status one of STATUSES. The call number is copied
// from the catalog as it is there.
import { readFileSync } from 'node:fs';
import { CsvError, parseCsv, type Record } from './csv.ts';
import { isDate } from './dates.ts';

export const HEADER = ['hold_id', 'branch', 'placed', 'title', 'call_number', 'status'];
export const STATUSES = ['waiting', 'ready', 'collected', 'cancelled'];

export interface Hold {
  id: number;
  branch: string;
  placed: string;
  title: string;
  callNumber: string;
  status: string;
  line: number;
}

export class HoldsError extends Error {}

/** What is wrong with one record of the export, or null. */
export function problem(fields: string[]): string | null {
  if (fields.length !== HEADER.length) return `expected ${HEADER.length} fields, found ${fields.length}`;
  const [id, branch, placed, title, , status] = fields;
  if (!/^[1-9][0-9]*$/.test(id)) return `bad hold id '${id}'`;
  if (branch === '') return 'no branch';
  if (!isDate(placed)) return `bad date '${placed}'`;
  if (title.trim() === '') return 'no title';
  if (!STATUSES.includes(status)) return `unknown status '${status}'`;
  return null;
}

/** The records of an export file, header left out; HoldsError when it cannot be read or is not CSV. */
export function readRecords(path: string): Record[] {
  let text: string;
  try {
    text = readFileSync(path, 'utf8');
  } catch (error) {
    throw new HoldsError(`cannot read ${path}: ${(error as NodeJS.ErrnoException).code ?? 'error'}`);
  }
  let records: Record[];
  try {
    records = parseCsv(text);
  } catch (error) {
    if (error instanceof CsvError) throw new HoldsError(`${path} ${error.message}`);
    throw error;
  }
  if (records.length > 0 && records[0].fields.join(',') === HEADER.join(',')) records = records.slice(1);
  return records;
}

/** Every hold in an export file; HoldsError naming the file and line of the first record that is not a hold. */
export function readHolds(path: string): Hold[] {
  return readRecords(path).map(({ line, fields }) => {
    const wrong = problem(fields);
    if (wrong) throw new HoldsError(`${path} line ${line}: ${wrong}`);
    const [id, branch, placed, title, callNumber, status] = fields;
    return { id: Number(id), branch, placed, title, callNumber, status, line };
  });
}
