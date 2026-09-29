-- Correct: one scalar subquery per column, no joins at all.
SELECT
    c.customer_id,
    c.name AS customer,
    (SELECT a.manager FROM account_assignments AS a
      WHERE a.customer_id = c.customer_id
      ORDER BY a.assigned_on DESC, a.assignment_id DESC LIMIT 1) AS account_manager,
    (SELECT COUNT(*) FROM orders AS o
      WHERE o.customer_id = c.customer_id AND o.order_date >= :start AND o.order_date < :end) AS order_count,
    (SELECT IFNULL(SUM(o.total_cents), 0) FROM orders AS o
      WHERE o.customer_id = c.customer_id AND o.order_date >= :start AND o.order_date < :end) AS revenue_cents,
    (SELECT MAX(o.order_date) FROM orders AS o
      WHERE o.customer_id = c.customer_id AND o.order_date >= :start AND o.order_date < :end) AS last_order_date
FROM customers AS c
ORDER BY revenue_cents DESC, c.customer_id;
