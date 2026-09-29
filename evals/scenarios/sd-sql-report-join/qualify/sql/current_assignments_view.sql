
-- The current assignment of each customer: latest assigned_on, then the higher assignment_id.
CREATE VIEW current_assignments AS
SELECT a.customer_id, a.manager
FROM account_assignments AS a
WHERE NOT EXISTS (
    SELECT 1
    FROM account_assignments AS b
    WHERE b.customer_id = a.customer_id
      AND (b.assigned_on > a.assigned_on
           OR (b.assigned_on = a.assigned_on AND b.assignment_id > a.assignment_id)));
