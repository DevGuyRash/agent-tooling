-- Correct: the period filter is part of the orders join condition and rows are grouped per customer;
-- the current assignment is the last row when a customer's assignments are ranked oldest first
-- (assigned_on ASC, assignment_id ASC).
WITH ranked AS (
    SELECT customer_id, manager,
           ROW_NUMBER() OVER (PARTITION BY customer_id
                              ORDER BY assigned_on ASC, assignment_id ASC) AS pos,
           COUNT(*) OVER (PARTITION BY customer_id) AS total
    FROM account_assignments
)
SELECT
    c.customer_id,
    c.name                          AS customer,
    r.manager                       AS account_manager,
    COUNT(o.order_id)               AS order_count,
    COALESCE(SUM(o.total_cents), 0) AS revenue_cents,
    MAX(o.order_date)               AS last_order_date
FROM customers AS c
LEFT JOIN ranked AS r ON r.customer_id = c.customer_id AND r.pos = r.total
LEFT JOIN orders AS o
       ON o.customer_id = c.customer_id
      AND o.order_date >= :start
      AND o.order_date <  :end
GROUP BY c.customer_id
ORDER BY revenue_cents DESC, c.customer_id;
