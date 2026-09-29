-- Customer activity for one period.
-- :start is the first day of the period and :end the day after it (ISO dates).
-- One row per customer, highest revenue first.
-- The period filter is part of the join condition, so customers without orders in the period keep
-- their row. The manager comes from a scalar subquery (the current assignment: latest assigned_on,
-- then higher assignment_id), so the assignment history never multiplies order rows.
SELECT
    c.customer_id,
    c.name                          AS customer,
    (SELECT a.manager
       FROM account_assignments AS a
      WHERE a.customer_id = c.customer_id
      ORDER BY a.assigned_on DESC, a.assignment_id DESC
      LIMIT 1)                      AS account_manager,
    COUNT(o.order_id)               AS order_count,
    COALESCE(SUM(o.total_cents), 0) AS revenue_cents,
    MAX(o.order_date)               AS last_order_date
FROM customers AS c
LEFT JOIN orders AS o
       ON o.customer_id = c.customer_id
      AND o.order_date >= :start
      AND o.order_date <  :end
GROUP BY c.customer_id
ORDER BY revenue_cents DESC, c.customer_id;
