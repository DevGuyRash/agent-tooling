// shelfwise: circulation desk tools.
import { parseArgs } from 'node:util';
import { checkReport } from './commands/check.ts';
import { holdsReport } from './commands/holds.ts';
import { pullList } from './commands/pull.ts';
import { HoldsError, readHolds, readRecords, STATUSES } from './holds.ts';

const USAGE = `usage: shelfwise holds --branch NAME [--status STATUS] HOLDS.csv
       shelfwise pull --branch NAME HOLDS.csv
       shelfwise check HOLDS.csv`;

function out(lines: string[]): void {
  if (lines.length) process.stdout.write(lines.join('\n') + '\n');
}

function fail(command: string, message: string): number {
  process.stderr.write(`shelfwise ${command}: ${message}\n`);
  return 2;
}

function usage(message?: string): number {
  if (message) process.stderr.write(`shelfwise: ${message}\n`);
  process.stderr.write(USAGE + '\n');
  return 2;
}

export function main(argv: string[]): number {
  const [command, ...rest] = argv;
  if (command === undefined || command === '--help' || command === '-h') {
    if (command === undefined) return usage();
    out([USAGE]);
    return 0;
  }
  let parsed;
  try {
    parsed = parseArgs({
      args: rest,
      allowPositionals: true,
      options: { branch: { type: 'string' }, status: { type: 'string' } },
    });
  } catch (error) {
    return usage((error as Error).message);
  }
  const { values, positionals } = parsed;
  try {
    switch (command) {
      case 'holds': {
        if (!values.branch || positionals.length !== 1) return usage();
        if (values.status !== undefined && !STATUSES.includes(values.status)) {
          return usage(`--status must be one of ${STATUSES.join(', ')}`);
        }
        out(holdsReport(readHolds(positionals[0]), values.branch, values.status));
        return 0;
      }
      case 'pull': {
        if (!values.branch || positionals.length !== 1 || values.status !== undefined) return usage();
        const list = pullList(readHolds(positionals[0]), values.branch);
        out(list.lines);
        return list.bad ? 1 : 0;
      }
      case 'check': {
        if (positionals.length !== 1 || values.branch !== undefined || values.status !== undefined) return usage();
        const report = checkReport(readRecords(positionals[0]));
        out(report.lines);
        return report.problems ? 1 : 0;
      }
      default:
        return usage(`unknown command '${command}'`);
    }
  } catch (error) {
    if (error instanceof HoldsError) return fail(command, error.message);
    throw error;
  }
}
