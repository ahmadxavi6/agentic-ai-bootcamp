## What this query does
This query retrieves customer information along with their lifetime value, last order date, and segment name for customers who meet specific criteria. It first joins the `customers`, `orders`, and `order_items` tables to gather relevant order data, then filters based on the year of the order, the customer's email domain, and other attributes. Finally, it sorts the results by lifetime value in descending order.

1. **FROM** `customers c`: Start with the `customers` table.
2. **JOIN** `orders o`: Join with the `orders` table on `customer_id` to get order details.
3. **JOIN** `order_items i`: Join with the `order_items` table on `order_id` to get item details for each order.
4. **LEFT JOIN** `customer_segments s`: Left join with `customer_segments` to get the segment name for each customer.
5. **WHERE** conditions are applied to filter results based on the year of the order, email domain, customer ID, country code, and account tier.
6. **Subqueries** are executed to calculate the lifetime value and last order date for each customer.
7. **ORDER BY** lifetime value in descending order.

## Findings
| Line | Pattern | Why it costs | Fix |
|------|---------|---------------|-----|
| 4 | SELECT * (SQL-01) | Fetching all columns can transfer unnecessary data and block covering indexes. | Specify only the columns needed instead of using `SELECT *`. |
| 17, 18 | Function on a filtered/joined column (SQL-02) | Using `YEAR(o.created_at)` prevents index seeking, leading to full table scans. | Change to `WHERE o.created_at >= '2024-01-01' AND o.created_at < '2025-01-01'`. |
| 18 | LIKE with a leading % (SQL-03) | The leading wildcard in `LIKE '%@acme.com'` prevents index usage, causing full scans. | Consider using a different approach, such as a trigram index, or filtering earlier. |
| 19 | Quoted literal compared to a numeric-looking column (SQL-04) | Comparing a string literal to a numeric column may cause implicit casting, which can drop index usage. | Ensure the literal matches the column type, e.g., use `c.customer_id = 10482`. |
| 5, 9 | Subquery in the SELECT list (SQL-05) | Each subquery runs for every row returned, leading to N+1 query execution. | Use a `LEFT JOIN` with a pre-aggregated table instead of subqueries. |
| 21 | NOT IN / IN (SELECT ...) (SQL-06) | `NOT IN` can return zero rows if the subquery yields NULL, and it blocks optimizations. | Replace with `NOT EXISTS` for better performance and correctness. |
| 24 | ORDER BY with no LIMIT (SQL-09) | Sorting the entire result set can lead to performance issues, especially with large datasets. | Add a `LIMIT` clause to restrict the number of rows returned. |
| 3 | DISTINCT (SQL-10) | Using `DISTINCT` can hide duplicates caused by joins, leading to unnecessary sorting. | Investigate the joins to eliminate duplicates before applying `DISTINCT`. |
| 20 | OR across columns (SQL-12) | Using `OR` across different columns can prevent the use of a composite index, leading to full scans. | Consider restructuring the query to use `UNION ALL` or separate conditions. |

## Rewritten query
```sql
SELECT DISTINCT
    c.customer_id, c.name, c.email, c.country_code, c.account_tier,  -- Specify only necessary columns
    lifetime_value, last_order_at, s.segment_name
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id
JOIN order_items i ON i.order_id = o.order_id
LEFT JOIN customer_segments s ON s.segment_id = c.segment_id
WHERE o.created_at >= '2024-01-01' AND o.created_at < '2025-01-01'
  AND LOWER(c.email) LIKE '%@acme.com'
  AND c.customer_id = '10482'
  AND (c.country_code = 'GB' OR c.account_tier = 'enterprise')
  AND NOT EXISTS (SELECT 1 FROM refunds r WHERE r.order_id = o.order_id)
ORDER BY lifetime_value DESC
LIMIT 100;  -- Add a limit to reduce sorting overhead
```

## What I could not verify
- The effectiveness of indexes on the `orders`, `customers`, and `refunds` tables. Confirm with `EXPLAIN` to see if the suggested indexes are being used.
- The actual row counts and data distribution in the tables, which could affect performance optimizations.