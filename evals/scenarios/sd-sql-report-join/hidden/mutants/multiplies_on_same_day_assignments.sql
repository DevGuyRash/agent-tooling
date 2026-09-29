-- Defect: the current assignment is the row whose assigned_on equals the customer's latest date,
-- so two assignments on that date both match: orders count twice and the manager is either one.
SELECT c.customer_id,
       c.name                          AS customer,
       a.manager                       AS account_manager,
       COUNT(o.order_id)               AS order_count,
       COALESCE(SUM(o.total_cents), 0) AS revenue_cents,
       MAX(o.order_date)               AS last_order_date
FROM customers AS c
LEFT JOIN account_assignments AS a
       ON a.customer_id = c.customer_id
      AND a.assigned_on = (SELECT MAX(x.assigned_on) FROM account_assignments AS x
                            WHERE x.customer_id = c.customer_id)
LEFT JOIN orders AS o
       ON o.customer_id = c.customer_id AND o.order_date >= :start AND o.order_date < :end
GROUP BY c.customer_id
ORDER BY revenue_cents DESC, c.customer_id;
