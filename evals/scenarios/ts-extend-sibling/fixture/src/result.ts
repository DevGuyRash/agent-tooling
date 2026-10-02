// What a command produces. main() writes it out; commands never write to the process streams themselves,
// so a failed command leaves standard output empty.

export interface Result {
  code: number;
  stdout: string;
  stderr: string;
}

export function ok(stdout: string): Result {
  return { code: 0, stdout, stderr: '' };
}

export function failure(stderr: string): Result {
  return { code: 1, stdout: '', stderr: stderr.endsWith('\n') ? stderr : `${stderr}\n` };
}

/** Exit status 2: the command line itself is wrong. */
export function usageError(command: string, message: string, usage: string): Result {
  return { code: 2, stdout: '', stderr: `hours ${command}: ${message}\n${usage}\n` };
}
