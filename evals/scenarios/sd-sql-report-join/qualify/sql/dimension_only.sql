-- Customer activity for one period.
-- :start is the first day of the period and :end the day after it (ISO dates).
-- One row per customer, highest revenue first.
WITH current_assignment AS (
    SELECT customer_id, manager
    FROM (
        SELECT customer_id, manager,
               ROW_NUMBER() OVER (PARTITION BY customer_id
                                  ORDER BY assigned_on DESC, assignment_id DESC) AS recency
        FROM account_assignments
    )
    WHERE recency = 1
)
SELECT
    c.customer_id,
    c.name                          AS customer,
    ca.manager                      AS account_manager,
    COUNT(o.order_id)               AS order_count,
    COALESCE(SUM(o.total_cents), 0) AS revenue_cents,
    MAX(o.order_date)               AS last_order_date
FROM customers AS c
LEFT JOIN current_assignment AS ca ON ca.customer_id = c.customer_id
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
WHERE o.order_date >= :start
  AND o.order_date <  :end
GROUP BY c.customer_id
ORDER BY revenue_cents DESC, c.customer_id;
