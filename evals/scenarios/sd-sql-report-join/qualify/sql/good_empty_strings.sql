-- Customer activity for one period.
-- :start is the first day of the period and :end the day after it (ISO dates).
-- One row per customer (orders aggregated inside the period, the current assignment by latest
-- assigned_on then higher assignment_id), both LEFT JOINed. "Empty" values, as the README calls them,
-- are empty strings: no manager, no last order.
WITH period_orders AS (
    SELECT customer_id, COUNT(*) AS order_count, SUM(total_cents) AS revenue_cents, MAX(order_date) AS last_order_date
    FROM orders
    WHERE order_date >= :start AND order_date < :end
    GROUP BY customer_id
),
current_assignment AS (
    SELECT customer_id, manager
    FROM (SELECT customer_id, manager,
                 ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY assigned_on DESC, assignment_id DESC) AS recency
          FROM account_assignments)
    WHERE recency = 1
)
SELECT
    c.customer_id,
    c.name                           AS customer,
    COALESCE(ca.manager, '')         AS account_manager,
    COALESCE(po.order_count, 0)      AS order_count,
    COALESCE(po.revenue_cents, 0)    AS revenue_cents,
    COALESCE(po.last_order_date, '') AS last_order_date
FROM customers AS c
LEFT JOIN current_assignment AS ca ON ca.customer_id = c.customer_id
LEFT JOIN period_orders      AS po ON po.customer_id = c.customer_id
ORDER BY revenue_cents DESC, c.customer_id;
