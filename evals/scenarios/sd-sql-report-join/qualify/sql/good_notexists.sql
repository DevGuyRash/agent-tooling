-- Customer activity for one period.
-- :start is the first day of the period and :end the day after it (ISO dates).
-- One row per customer, highest revenue first.
-- Current assignment = the assignment no later assignment supersedes (by assigned_on, then
-- assignment_id). Orders are aggregated per customer inside the period before the join.
SELECT
    c.customer_id,
    c.name                       AS customer,
    a.manager                    AS account_manager,
    COALESCE(t.order_count, 0)   AS order_count,
    COALESCE(t.revenue_cents, 0) AS revenue_cents,
    t.last_order_date            AS last_order_date
FROM customers AS c
LEFT JOIN account_assignments AS a
       ON a.customer_id = c.customer_id
      AND NOT EXISTS (
          SELECT 1
          FROM account_assignments AS later
          WHERE later.customer_id = a.customer_id
            AND (later.assigned_on > a.assigned_on
                 OR (later.assigned_on = a.assigned_on AND later.assignment_id > a.assignment_id)))
LEFT JOIN (
    SELECT customer_id,
           COUNT(*)         AS order_count,
           SUM(total_cents) AS revenue_cents,
           MAX(order_date)  AS last_order_date
    FROM orders
    WHERE order_date >= :start AND order_date < :end
    GROUP BY customer_id
) AS t ON t.customer_id = c.customer_id
ORDER BY revenue_cents DESC, c.customer_id;
