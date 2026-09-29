-- Customer activity for one period.
-- :start is the first day of the period and :end the day after it (ISO dates).
-- One row per customer, highest revenue first.
SELECT
    customer_id,
    customer,
    account_manager,
    COUNT(order_date)             AS order_count,
    COALESCE(SUM(total_cents), 0) AS revenue_cents,
    MAX(order_date)               AS last_order_date
FROM (
    -- the assignment join repeats each order once per assignment row; group the repeats back together
    SELECT c.customer_id, c.name AS customer, MAX(a.manager) AS account_manager, o.order_date, o.total_cents
    FROM customers AS c
    LEFT JOIN account_assignments AS a ON a.customer_id = c.customer_id
    LEFT JOIN orders AS o
           ON o.customer_id = c.customer_id
          AND o.order_date >= :start
          AND o.order_date <  :end
    GROUP BY c.customer_id, o.order_date, o.total_cents
)
GROUP BY customer_id
ORDER BY revenue_cents DESC, customer_id;
