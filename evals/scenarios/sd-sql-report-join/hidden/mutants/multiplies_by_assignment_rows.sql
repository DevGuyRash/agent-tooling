-- Defect: the raw assignment history is joined alongside the orders, so each order counts once per
-- assignment row of its customer. The manager column itself is correct.
WITH ranked_assignments AS (
    SELECT customer_id, manager,
           ROW_NUMBER() OVER (PARTITION BY customer_id
                              ORDER BY assigned_on DESC, assignment_id DESC) AS pos
    FROM account_assignments
)
SELECT c.customer_id,
       c.name                          AS customer,
       r.manager                       AS account_manager,
       COUNT(o.order_id)               AS order_count,
       COALESCE(SUM(o.total_cents), 0) AS revenue_cents,
       MAX(o.order_date)               AS last_order_date
FROM customers AS c
LEFT JOIN ranked_assignments AS r ON r.customer_id = c.customer_id AND r.pos = 1
LEFT JOIN account_assignments AS a ON a.customer_id = c.customer_id
LEFT JOIN orders AS o
       ON o.customer_id = c.customer_id AND o.order_date >= :start AND o.order_date < :end
GROUP BY c.customer_id
ORDER BY revenue_cents DESC, c.customer_id;
