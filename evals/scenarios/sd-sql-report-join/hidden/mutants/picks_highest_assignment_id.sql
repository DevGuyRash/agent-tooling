-- Defect: the current assignment is the customer's highest assignment_id (the latest entry), which is
-- not the latest assigned_on when an assignment was recorded late with an earlier date. Everything
-- else is correct.
WITH period AS (
    SELECT customer_id, COUNT(order_id) AS n, SUM(total_cents) AS cents, MAX(order_date) AS last_date
    FROM orders
    WHERE order_date >= :start AND order_date < :end
    GROUP BY customer_id
)
SELECT c.customer_id,
       c.name              AS customer,
       a.manager           AS account_manager,
       IFNULL(p.n, 0)      AS order_count,
       IFNULL(p.cents, 0)  AS revenue_cents,
       p.last_date         AS last_order_date
FROM customers AS c
LEFT JOIN account_assignments AS a
       ON a.assignment_id = (SELECT MAX(x.assignment_id) FROM account_assignments AS x
                              WHERE x.customer_id = c.customer_id)
LEFT JOIN period AS p ON p.customer_id = c.customer_id
ORDER BY revenue_cents DESC, c.customer_id;
