-- Customer activity for one period.
-- :start is the first day of the period and :end the day after it (ISO dates).
--
-- Grain: one row per customer. Both inputs are reduced to that grain before they are joined:
--   * orders -> one row per customer with orders in the period (period filter applied here, so it
--     cannot remove customers from the outer join);
--   * account_assignments holds one row per assignment event (reassignments, duplicate syncs,
--     same-day corrections), so it is reduced to the current assignment: the latest entry
--     (highest assignment_id).
-- Both joins are LEFT JOINs, so customers without orders in the period or without an assignment
-- keep their row with zero activity or no manager. Highest revenue first, ties by customer id.
WITH period_orders AS (
    SELECT customer_id,
           COUNT(*)         AS order_count,
           SUM(total_cents) AS revenue_cents,
           MAX(order_date)  AS last_order_date
    FROM orders
    WHERE order_date >= :start
      AND order_date <  :end
    GROUP BY customer_id
),
current_assignment AS (
    SELECT customer_id, manager
    FROM (
        SELECT customer_id,
               manager,
               ROW_NUMBER() OVER (
                   PARTITION BY customer_id
                   ORDER BY assignment_id DESC
               ) AS recency
        FROM account_assignments
    )
    WHERE recency = 1
)
SELECT
    c.customer_id,
    c.name                        AS customer,
    ca.manager                    AS account_manager,
    COALESCE(po.order_count, 0)   AS order_count,
    COALESCE(po.revenue_cents, 0) AS revenue_cents,
    po.last_order_date            AS last_order_date
FROM customers AS c
LEFT JOIN current_assignment AS ca ON ca.customer_id = c.customer_id
LEFT JOIN period_orders      AS po ON po.customer_id = c.customer_id
ORDER BY revenue_cents DESC, c.customer_id;
