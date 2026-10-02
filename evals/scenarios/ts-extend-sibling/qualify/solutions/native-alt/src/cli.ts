// The hours command line: hours COMMAND [ARGS].

import { check } from './commands/check.ts';
import { report } from './commands/report.ts';
import type { Result } from './result.ts';

const USAGE = `usage: hours COMMAND [ARGS]

commands:
  check FILE...    check timesheets: every line is an entry, no ranges overlap
  report [--from DATE] [--to DATE] [--by project|client|date] FILE...
                   time per project, client, or date
  invoice --client CLIENT --rates FILE (--month YYYY-MM | --from DATE --to DATE) FILE...
                   an invoice for one client
`;

const COMMANDS: Record<string, (args: string[]) => Result | Promise<Result>> = {
  check,
  report,
  invoice: async (args) => (await import('./commands/invoice.ts')).invoice(args),
};

export async function main(argv: string[]): Promise<number> {
  const [command, ...args] = argv;
  if (command === 'help' || command === '--help' || command === '-h') {
    process.stdout.write(USAGE);
    return 0;
  }
  if (command === undefined) {
    process.stderr.write(USAGE);
    return 2;
  }
  if (!Object.hasOwn(COMMANDS, command)) {
    process.stderr.write(`hours: unknown command "${command}"\n${USAGE}`);
    return 2;
  }
  const result = await COMMANDS[command](args);
  process.stdout.write(result.stdout);
  process.stderr.write(result.stderr);
  return result.code;
}
