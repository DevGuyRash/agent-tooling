-- Sales database schema. The reports only read from it.

CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    created_on  TEXT NOT NULL              -- date the account was opened (YYYY-MM-DD)
);

-- Account manager assignments, synced from the CRM. Reassigning an account adds a row.
CREATE TABLE account_assignments (
    assignment_id INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL REFERENCES customers (customer_id),
    manager       TEXT    NOT NULL,
    assigned_on   TEXT    NOT NULL         -- date the assignment took effect (YYYY-MM-DD)
);
CREATE INDEX account_assignments_customer ON account_assignments (customer_id);

CREATE TABLE orders (
    order_id    INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers (customer_id),
    order_date  TEXT    NOT NULL,          -- YYYY-MM-DD
    total_cents INTEGER NOT NULL CHECK (total_cents >= 0)
);
CREATE INDEX orders_customer_date ON orders (customer_id, order_date);
