-- Customer activity for one period.
-- :start is the first day of the period and :end the day after it (ISO dates).
-- One row per customer, highest revenue first. current_assignments (schema.sql) has at most one row
-- per customer; the period filter belongs to the orders join so customers without orders stay.
SELECT
    c.customer_id,
    c.name                          AS customer,
    ca.manager                      AS account_manager,
    COUNT(o.order_id)               AS order_count,
    COALESCE(SUM(o.total_cents), 0) AS revenue_cents,
    MAX(o.order_date)               AS last_order_date
FROM customers AS c
LEFT JOIN current_assignments AS ca
       ON ca.customer_id = c.customer_id
LEFT JOIN orders AS o
       ON o.customer_id = c.customer_id
      AND o.order_date >= :start
      AND o.order_date <  :end
GROUP BY c.customer_id
ORDER BY revenue_cents DESC, c.customer_id;
