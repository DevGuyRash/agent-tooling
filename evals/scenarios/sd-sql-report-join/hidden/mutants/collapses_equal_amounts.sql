-- Defect: revenue sums each distinct order amount once per customer (what SUM(DISTINCT total_cents)
-- does), so separate orders of equal amount count once. Order counts and everything else are correct.
WITH ranked_assignments AS (
    SELECT customer_id, manager,
           ROW_NUMBER() OVER (PARTITION BY customer_id
                              ORDER BY assigned_on DESC, assignment_id DESC) AS pos
    FROM account_assignments
),
period AS (
    SELECT o.customer_id,
           COUNT(*) AS n,
           (SELECT SUM(amount) FROM (SELECT x.total_cents AS amount FROM orders AS x
                                      WHERE x.customer_id = o.customer_id
                                        AND x.order_date >= :start AND x.order_date < :end
                                      GROUP BY x.total_cents)) AS cents,
           MAX(o.order_date) AS last_date
    FROM orders AS o
    WHERE o.order_date >= :start AND o.order_date < :end
    GROUP BY o.customer_id
)
SELECT c.customer_id,
       c.name              AS customer,
       r.manager           AS account_manager,
       IFNULL(p.n, 0)      AS order_count,
       IFNULL(p.cents, 0)  AS revenue_cents,
       p.last_date         AS last_order_date
FROM customers AS c
LEFT JOIN ranked_assignments AS r ON r.customer_id = c.customer_id AND r.pos = 1
LEFT JOIN period AS p ON p.customer_id = c.customer_id
ORDER BY revenue_cents DESC, c.customer_id;
