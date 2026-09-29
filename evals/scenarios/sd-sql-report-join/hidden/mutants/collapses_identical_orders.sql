-- Defect: orders are deduplicated on (customer, date, amount) before counting, so two real orders
-- that match on all three count as one. Everything else is correct.
WITH ranked_assignments AS (
    SELECT customer_id, manager,
           ROW_NUMBER() OVER (PARTITION BY customer_id
                              ORDER BY assigned_on DESC, assignment_id DESC) AS pos
    FROM account_assignments
),
period AS (
    SELECT customer_id, COUNT(*) AS n, SUM(total_cents) AS cents, MAX(order_date) AS last_date
    FROM (SELECT customer_id, order_date, total_cents
          FROM orders
          WHERE order_date >= :start AND order_date < :end
          GROUP BY customer_id, order_date, total_cents)
    GROUP BY customer_id
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
