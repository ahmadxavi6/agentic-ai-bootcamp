-- Inherited from a contractor who left in March. No comments, no ticket.
-- Runs nightly, used to take 4 minutes, now takes 40.
SELECT DISTINCT
    c.*,
    (SELECT SUM(oi.quantity * oi.unit_price)
       FROM order_items oi
       JOIN orders o2 ON o2.order_id = oi.order_id
      WHERE o2.customer_id = c.customer_id) AS lifetime_value,
    (SELECT MAX(o3.created_at)
       FROM orders o3
      WHERE o3.customer_id = c.customer_id) AS last_order_at,
    s.segment_name
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id
JOIN order_items i ON i.order_id = o.order_id
LEFT JOIN customer_segments s ON s.segment_id = c.segment_id
WHERE YEAR(o.created_at) = 2024
  AND LOWER(c.email) LIKE '%@acme.com'
  AND c.customer_id = '10482'
  AND (c.country_code = 'GB' OR c.account_tier = 'enterprise')
  AND o.order_id NOT IN (
        SELECT r.order_id FROM refunds r
      )
ORDER BY lifetime_value DESC
