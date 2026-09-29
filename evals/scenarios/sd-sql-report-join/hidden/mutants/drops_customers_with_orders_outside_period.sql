-- Defect: the WHERE filter keeps customers with no orders at all (OR ... IS NULL) but still drops
-- customers whose orders all fall outside the period. Everything else is correct.
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
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
WHERE (o.order_date >= :start AND o.order_date < :end) OR o.order_id IS NULL
GROUP BY c.customer_id
ORDER BY revenue_cents DESC, c.customer_id;
