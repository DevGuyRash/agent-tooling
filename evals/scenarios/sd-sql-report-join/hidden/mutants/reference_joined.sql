-- Correct: the current assignment is the highest assignment_id among the customer's rows on its latest
-- assigned_on, joined straight from account_assignments; the period's orders are aggregated in a derived
-- table (WHERE o.order_date ...) before the join. COUNT(DISTINCT o.order_id) loses nothing: order_id is
-- the key. Written with the tokens text-only guards tend to forbid, so such guards fail a correct query.
SELECT
    c.customer_id,
    c.name AS customer,
    a.manager AS account_manager,
    CASE WHEN p.n IS NULL THEN 0 ELSE p.n END AS order_count,
    CASE WHEN p.cents IS NULL THEN 0 ELSE p.cents END AS revenue_cents,
    p.last_date AS last_order_date
FROM customers AS c
LEFT JOIN account_assignments AS a
       ON a.customer_id = c.customer_id
      AND a.assignment_id = (
          SELECT MAX(x.assignment_id)
          FROM account_assignments AS x
          WHERE x.customer_id = c.customer_id
            AND x.assigned_on = (SELECT MAX(y.assigned_on) FROM account_assignments AS y
                                  WHERE y.customer_id = c.customer_id))
LEFT JOIN (
    SELECT o.customer_id,
           COUNT(DISTINCT o.order_id) AS n,
           SUM(o.total_cents)         AS cents,
           MAX(o.order_date)          AS last_date
    FROM orders AS o
    WHERE o.order_date >= :start AND o.order_date < :end
    GROUP BY o.customer_id
) AS p ON p.customer_id = c.customer_id
ORDER BY revenue_cents DESC, c.customer_id;
