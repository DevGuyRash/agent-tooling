# toolroom specification

toolroom keeps the books of a neighbourhood tool library: which tools are lent to which members, which loans are overdue, and what is owed for them. This file is the requirement. Each numbered line is one requirement; the numbers are stable.

## Scope

- **R1.** toolroom runs on the library's desk computer, by hand or from the nightly job. The data files are written by the desk software and are trusted. A run handles at most 500 loans, 200 tools and 300 members.

## Data

- **R2.** The data directory (`--data DIR`, default: the current directory) holds three CSV files, each with a header row. `members.csv`: `id,name,status`, where `status` is `standard` or `supporter`. `tools.csv`: `id,name,value`, where `value` is the tool's replacement value in cents. `loans.csv`: `loan,member,tool,out,due,returned`. Dates are `YYYY-MM-DD`. `returned` is empty while the tool is still out.
- **R3.** A file that cannot be read, or a row that cannot be understood (the wrong number of columns, a bad date or number, an unknown status, a member or tool the other files do not list), stops the run before anything is printed: the exit status is 2 and standard error names the file and the line.

## Commands

- **R4.** `python3 -m toolroom [--data DIR] [--today DATE] COMMAND`. `DATE` is `YYYY-MM-DD` and defaults to the day the program runs. The exit status is 0 when the command finishes and 2 for wrong arguments or unusable data.
- **R5.** `out` prints the loans that are still out, oldest due date first and then by loan id, one per line: loan id, member name, tool name and due date, separated by two spaces.

## Overdue

- **R6.** A loan that is still out is overdue when today is later than its due date; its days overdue are the whole days from the due date to today. A loan due today is not overdue, and a loan that has been returned never is.
- **R7.** The fine for an overdue loan is 50 cents for each day overdue, but never more than the tool's replacement value. A supporter pays three quarters of that fine, rounded to the nearest cent, halves rounded up.
- **R8.** `overdue` prints the overdue loans, most days overdue first; loans with the same number of days are ordered by member name, A to Z, and then by loan id.
- **R9.** `overdue` prints one line per loan: loan id, member name, tool name, days overdue and fine, separated by two spaces, the fine in dollars and cents (`1.50`). With `--format csv` it prints CSV instead: the header row `loan,member,tool,days,fine` and one row per loan, with the fine in the same form.
- **R10.** With `--notices DIR`, `overdue` also writes a notice for every member who has an overdue loan, to `DIR/<member id>.txt` (the directory is created if it does not exist). A notice greets the member by name, lists the member's overdue loans in the order of R8 (tool name, days overdue, fine), and ends with the total the member owes: the sum of those fines.
- **R11.** Writing a notice is attempted up to three times, one second apart, because the library's backup program briefly locks files in the notices directory. A notice that cannot be written by the third attempt is skipped: `could not write notice for <member id>: <error>` goes to standard error and the run goes on with the next member. A skipped notice does not change the exit status.
