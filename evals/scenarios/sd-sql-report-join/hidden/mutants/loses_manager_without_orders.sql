-- Defect: the manager is carried inside the per-customer order aggregate, so a customer without orders in
-- the period is listed with zero activity but no manager. Everything else is correct.
WITH ranked_assignments AS (
    SELECT customer_id, manager,
           ROW_NUMBER() OVER (PARTITION BY customer_id
                              ORDER BY assigned_on DESC, assignment_id DESC) AS pos
    FROM account_assignments
),
period AS (
    SELECT o.customer_id, r.manager,
           COUNT(o.order_id) AS n, SUM(o.total_cents) AS cents, MAX(o.order_date) AS last_date
    FROM orders AS o
    LEFT JOIN ranked_assignments AS r ON r.customer_id = o.customer_id AND r.pos = 1
    WHERE o.order_date >= :start AND o.order_date < :end
    GROUP BY o.customer_id, r.manager
)
SELECT c.customer_id,
       c.name              AS customer,
       p.manager           AS account_manager,
       IFNULL(p.n, 0)      AS order_count,
       IFNULL(p.cents, 0)  AS revenue_cents,
       p.last_date         AS last_order_date
FROM customers AS c
LEFT JOIN period AS p ON p.customer_id = c.customer_id
ORDER BY revenue_cents DESC, c.customer_id;
