-- Customer activity for one period.
-- :start is the first day of the period and :end the day after it (ISO dates).
-- The current assignment (latest assigned_on, then higher assignment_id) is looked up while the period's
-- orders are aggregated, and the aggregate is LEFT JOINed to customers.
WITH current_assignment AS (
    SELECT customer_id, manager
    FROM (SELECT customer_id, manager,
                 ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY assigned_on DESC, assignment_id DESC) AS recency
          FROM account_assignments)
    WHERE recency = 1
),
period AS (
    SELECT o.customer_id,
           ca.manager,
           COUNT(*)           AS order_count,
           SUM(o.total_cents) AS revenue_cents,
           MAX(o.order_date)  AS last_order_date
    FROM orders AS o
    LEFT JOIN current_assignment AS ca ON ca.customer_id = o.customer_id
    WHERE o.order_date >= :start AND o.order_date < :end
    GROUP BY o.customer_id, ca.manager
)
SELECT
    c.customer_id,
    c.name                       AS customer,
    p.manager                    AS account_manager,
    COALESCE(p.order_count, 0)   AS order_count,
    COALESCE(p.revenue_cents, 0) AS revenue_cents,
    p.last_order_date            AS last_order_date
FROM customers AS c
LEFT JOIN period AS p ON p.customer_id = c.customer_id
ORDER BY revenue_cents DESC, c.customer_id;
