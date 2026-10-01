# Routing files

The paging service sends every alert through `routing/main.routes`, and the files it includes, which it loads when this repository is deployed. `tools/routes.py` reads routing files by the same rules, so on-call can check a change and try alerts against it before it goes out (see the README).

## Lines

A routing file is UTF-8 text with one statement per line; lines end in LF or CRLF. Spaces and tabs at the start and end of a line are ignored, and so are empty lines and lines whose first character is `#`. A `#` anywhere else is ordinary text (chat channels start with one). The words of a line are separated by one or more spaces or tabs.

A block opens with a line ending in `{` and closes with a line holding only `}`.

## The main file and includes

The main file holds receiver blocks, include lines, and exactly one `route` block: the root route.

`include "PATH"` reads another routing file. PATH is relative to the directory of the file that holds the include line (or absolute). An included file may hold receiver blocks, include lines, and any number of route blocks. Its receivers join all the others, wherever the include line is. Its route blocks become child routes of the route that holds the include line, at the include line's place among that route's other children. So a file with route blocks can only be included inside a route; an include line outside any route is for files of receivers.

Each file is read once. An include of a file that has already been read is skipped, wherever it is. An include of a file that is still being read (it includes itself, directly or through other files) is an error. Two paths name the same file when they lead to the same file once symbolic links are followed.

## Receivers

```
receiver payments-oncall {
  page payments-primary
  chat #payments-alerts
  ticket PAY
}
```

A receiver's name is lowercase letters, digits, and `-`, starting with a letter or digit, and each name is defined once across all the files. The lines in a receiver say where its alerts go: `page SCHEDULE` (an on-call schedule), `chat CHANNEL`, and `ticket QUEUE`, each followed by one word. A receiver with no lines is allowed; alerts sent to it reach nobody.

## Routes

```
route {
  receiver platform-oncall
  route {
    match team = payments
    receiver payments-oncall
    include "teams/payments.routes"
  }
  route {
    match severity = info
    during mon-fri 09:00-17:00
    receiver platform-tickets
    continue
  }
}
```

| Line | Meaning |
| --- | --- |
| `receiver NAME` | Where this route sends alerts. A route without one sends them to its parent route's receiver (its own or, in turn, its parent's). At most once in a route. |
| `match LABEL OP VALUE` | A condition on one of the alert's labels. OP is `=` (equals VALUE), `!=` (does not equal it), `~` (matches the pattern VALUE), or `!~` (does not match it). LABEL is lowercase letters, digits, and `_`, not starting with a digit. VALUE is one word. In a pattern, `*` stands for any run of characters, none included, every other character stands for itself, and the pattern must match the whole value. |
| `during DAYS FROM-TO` | A time window, in UTC. DAYS is a day (`mon`, `tue`, `wed`, `thu`, `fri`, `sat`, `sun`), a range of days such as `mon-fri` (a range may wrap past Sunday: `fri-mon` is Friday to Monday), or several of these separated by commas, such as `mon-thu,sat`. FROM and TO are times `HH:MM`, FROM earlier than TO and TO at most `24:00`. The window is from FROM up to but not including TO, on each of those days. |
| `continue` | After this route has taken an alert, the routes after it are tried too. At most once in a route. |
| `route {` ... `}` | A child route. |
| `include "PATH"` | The route blocks of another file, as child routes here. |

An alert has labels, each a name and a value, and the time it fired. A label the alert does not have counts as having the empty value: `match team != payments` holds for an alert without a team label, and `match team = payments` does not.

A route matches an alert when all of its `match` lines hold and, if it has `during` lines, the alert fired within at least one of them. The root route matches every alert: it cannot have `match`, `during`, or `continue` lines, and it must have a receiver.

## Where an alert goes

An alert starts at the root route. A route that has the alert tries its child routes in order. A child that matches takes the alert, and the children after it are tried only if that child has `continue`. When none of its children matches, the route sends the alert to its receiver.

So an alert goes to one receiver, or to several when `continue` lets more than one route take it. The receivers are listed in the order the routes sent the alert to them, each once.

## Errors

The first error stops the reading. It is reported as `FILE:LINE: MESSAGE`. FILE is the main file's path as it was given, and for an included file, the include's PATH joined to the directory part of the including file's FILE, as written (an absolute PATH is used as it is). Lines are read in order, an included file's lines at its include line. A block left open is found at the end of its file, a root route without a receiver when the root route closes, and unknown receivers once all the files have been read, in the order their lines were read.

| Message | When |
| --- | --- |
| `unexpected "WORD"` | The first word of the line is not a statement allowed where it stands, such as `}` outside a block or `match` in a receiver. |
| `expected: FORM` | A statement with the wrong words. FORM is the statement's form: `include "PATH"`, `receiver NAME {`, `route {`, `}`, `receiver NAME` (in a route), `match LABEL OP VALUE`, `during DAYS FROM-TO`, `continue`, `page SCHEDULE`, `chat CHANNEL`, or `ticket QUEUE`. |
| `bad receiver name "NAME"` | A receiver block's name is not a valid name. |
| `bad label "LABEL"` | |
| `bad operator "OP"` | |
| `bad days "DAYS"` | |
| `bad time window "FROM-TO"` | Including a window whose FROM is not earlier than its TO. |
| `receiver "NAME" is already defined at FILE:LINE` | FILE:LINE is where it was defined first. |
| `"receiver" given twice in one route` | Likewise `"continue" given twice in one route`. |
| `block is not closed` | At the line that opened the innermost block still open at the end of its file. |
| `cannot read "PATH"` | At an include line whose file cannot be read; PATH as written in the include. |
| `include cycle at "PATH"` | At an include line naming a file that is still being read. |
| `"PATH" has routes; include it inside a route` | At an include line outside any route, when the included file has a route block. |
| `second root route` | At a second route block outside any route in the main file. |
| `the root route cannot have "match"` | Likewise `"during"` and `"continue"`. |
| `the root route has no receiver` | At the root route's `route {` line. |
| `unknown receiver "NAME"` | At a route's `receiver NAME` line, when no receiver block has that name. |

Two errors have no line: `FILE: cannot read`, when the main file cannot be read, and `FILE: no root route`, when the main file has no route block.
