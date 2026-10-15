# shopdesk specification

shopdesk is a small shop back office made of three independent packages: `inventory`, `orders` and `billing`. Each is a command-line tool over its own JSON file. This file specifies all three.

## 0. Conventions

- Run a package as `python3 -m <package> [--data DIR] <command> [arguments]`. `DIR` defaults to `$SHOPDESK_DATA`, then `~/.shopdesk`.
- A package keeps its state in one file in `DIR`, named after the package (`inventory.json`, `orders.json`, `billing.json`). A missing file is the empty state. A command writes the file only when it succeeds.
- A result is printed on standard output. A command that cannot do what was asked prints `error: <message>` on standard error and exits with status 1. A malformed command line (a wrong number of arguments, a quantity or amount that is not valid, an unknown option value) exits with status 2 and prints `error: <message>` the same way. A command line is checked before the state is looked at, so a problem with the arguments is reported (status 2) before a problem with the state (status 1).
- A quantity is a positive integer written in digits (`3`, not `0`, `-3`, `+3`, `3.0` or `three`). Anything else is `error: quantity must be a positive integer`, status 2.
- Packages use only the Python standard library and do not import each other. Connecting them is a later step outside this specification.
- Each package has its tests in `tests/test_<package>.py`. `make check` runs all of them.

## 1. inventory

State: `{"items": {"<SKU>": <stock>}}`. A SKU is any non-empty argument; stock is a non-negative integer.

### 1.1 add SKU QTY

Adds QTY units to SKU's stock, creating the SKU when it is new. Prints `added <QTY> <SKU>, <n> in stock`, where n is the stock after adding. Usage: `error: usage: inventory add SKU QTY`.

### 1.2 stock [SKU]

With a SKU, prints `<SKU> <n>`; an unknown SKU is `error: unknown SKU <SKU>`. Without one, prints one `<SKU> <n>` line per SKU in alphabetical order, and nothing at all when there are none. Usage: `error: usage: inventory stock [SKU]`.

### 1.3 remove SKU QTY

Takes QTY units out of SKU's stock. Prints `removed <QTY> <SKU>, <n> left`, where n is the stock after removing. A SKU whose stock reaches 0 stays listed with 0; it is not deleted.

- An unknown SKU is `error: unknown SKU <SKU>`.
- Removing more than is in stock is `error: only <n> of <SKU> in stock`, where n is the current stock; nothing changes.
- Usage: `error: usage: inventory remove SKU QTY`.

## 2. orders

State: `{"next": <id>, "orders": {"<id>": {"customer": "<name>", "lines": [{"sku": "<SKU>", "qty": <n>}], "status": "open"}}}`. Ids count up from 1. A status is `open`, `shipped` or `cancelled`.

### 2.1 place CUSTOMER SKU:QTY [SKU:QTY ...]

Creates an open order with the next id. Prints `placed order <id> for <CUSTOMER>`. An argument without a colon, or with an empty SKU, is `error: bad line "<argument>": expected SKU:QTY`, status 2. Usage: `error: usage: orders place CUSTOMER SKU:QTY [SKU:QTY ...]`.

### 2.2 show ID

Prints `order <id> <customer> <status>`, then one `  <SKU> x<QTY>` line per line of the order. An unknown id is `error: no such order <ID>`. Usage: `error: usage: orders show ID`.

### 2.3 cancel ID

Cancels an open order. Prints `cancelled order <id>`.

- An unknown id is `error: no such order <ID>`.
- A cancelled order is `error: order <id> is already cancelled`; a shipped one is `error: order <id> has shipped`. Nothing changes.
- Usage: `error: usage: orders cancel ID`.

### 2.4 list [--status STATUS]

Prints one line per order in id order: `<id> <customer> <status> <n> lines`, with `1 line` for a single line. With `--status`, only orders with that status. A status other than the three above is `error: unknown status <value>`, status 2. Prints nothing when no order matches. Usage: `error: usage: orders list [--status STATUS]`.

### 2.5 ship ID

Ships an open order. Prints `shipped order <id>`. An unknown id is `error: no such order <ID>`; a cancelled order is `error: order <id> is cancelled`; a shipped one is `error: order <id> has already shipped`. Nothing changes. Usage: `error: usage: orders ship ID`.

## 3. billing

State: `{"invoices": {"<order id>": {"total_cents": <n>, "paid_cents": <n>}}}`. An amount is written with exactly two decimals (`12.50`); anything else is `error: amount must look like 12.50`, status 2. Amounts are printed the same way. What is due on an invoice is its total minus what it has paid.

### 3.1 invoice ORDER_ID AMOUNT

Creates the invoice for an order with nothing paid. Prints `invoiced order <id>: <AMOUNT> due`. An order that already has an invoice is `error: order <id> is already invoiced`. Usage: `error: usage: billing invoice ORDER_ID AMOUNT`.

### 3.2 pay ORDER_ID AMOUNT

Records a payment. Prints `paid <AMOUNT> on order <id>, <DUE> due`, where DUE is what is due afterwards. An order without an invoice is `error: order <id> is not invoiced`; a payment above what is due is `error: payment exceeds the <DUE> due`. Usage: `error: usage: billing pay ORDER_ID AMOUNT`.

### 3.3 refund ORDER_ID AMOUNT

Takes a payment back. Prints `refunded <AMOUNT> on order <id>, <DUE> due`. An order without an invoice is `error: order <id> is not invoiced`; a refund above what was paid is `error: only <PAID> paid on order <id>`. Usage: `error: usage: billing refund ORDER_ID AMOUNT`.

### 3.4 balance

Prints `outstanding <TOTAL>`, the sum of what is due on every invoice (`outstanding 0.00` when there are none). Usage: `error: usage: billing balance`.
