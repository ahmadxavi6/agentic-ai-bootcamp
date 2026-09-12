# SQL Optimisation Checklist

The *why* behind every code `scan_sql.py` emits: the cost mechanism, the fix,
and when the pattern is fine and should be left alone. That last line matters —
a checklist applied without judgement is cargo cult.

## SQL-01 — `SELECT *`
**Costs:** every column crosses the wire, including `TEXT`/`BLOB` you never
read. It also blocks *covering indexes* — the engine could have answered from
the index alone, but must now visit the heap row for the extra columns.
**Fix:** list the columns actually used downstream.
**Fine when:** ad-hoc exploration, or a small lookup table you need whole.

## SQL-02 — Function wrapped around a filtered column
**Costs:** `WHERE YEAR(created_at) = 2024` is *non-sargable*. The index is
ordered by raw value, not by `YEAR(...)`, so the engine cannot seek — it
computes the function for every row. B-tree seek becomes full scan.
**Fix:** a range over the bare column:
`created_at >= '2024-01-01' AND created_at < '2025-01-01'`. For
`UPPER(email) = 'X'`, compare consistently or add an expression index.
**Fine when:** the function wraps a constant (`= DATE('now')`), or tiny table.

## SQL-03 — Leading-wildcard `LIKE '%foo'`
**Costs:** a B-tree is sorted left-to-right. With an unknown prefix there is no
starting point to seek to, so it scans every row.
**Fix:** depends on the shape. A trailing-only wildcard (`'foo%'`) seeks fine.
A **suffix** match like `'%@acme.com'` has no index-friendly rewrite — you need
a trigram/full-text index, or an index on a reversed or extracted column
(e.g. store `email_domain` and match it with `=`).
**Do not "fix" it by deleting the `%`** — `LIKE '@acme.com'` is an equality test
that returns different rows. A fix that changes the result set is not a fix.
**Fine when:** small table, or already filtered to few rows by another predicate.

## SQL-04 — Implicit cast (quoted literal against a numeric column)
**Costs:** `WHERE user_id = '123'` forces a type coercion. Depending on the
engine's coercion direction, the *column* gets cast — which is SQL-02 with an
invisible function, and the index is dropped. MySQL is especially prone to this.
**Fix:** match the literal to the column type: `user_id = 123`.
**Fine when:** the column really is a string type. Confirm before "fixing".

## SQL-05 — Scalar subquery in the SELECT list
**Costs:** this is N+1 inside the database. One correlated execution per output
row: 50k rows → 50k subquery executions. Planners sometimes decorrelate it,
often they do not.
**Fix:** a `LEFT JOIN` against a pre-aggregated derived table or CTE, so the
inner work happens once over the whole set.
**Fine when:** the outer query returns a handful of rows.

## SQL-06 — `IN (SELECT ...)` and `NOT IN (SELECT ...)`
**Costs:** `IN` is usually optimised to a semi-join and is fine. `NOT IN` is the
trap — it has a **correctness** bug, not just a speed one: if the subquery
returns a single `NULL`, the whole predicate is `UNKNOWN` and you get **zero
rows**. It also blocks anti-join optimisation.
**Fix:** `NOT EXISTS` — NULL-safe and usually the better plan. Or
`LEFT JOIN ... WHERE key IS NULL`.
**Fine when:** `IN` with a literal list, or a subquery column that is `NOT NULL`.

## SQL-07 — No `WHERE` and no `LIMIT`
**Costs:** unbounded scan, plus an unbounded result set travelling to the
client. Cost grows with the table forever: passes in dev, pages someone in prod.
**Fix:** a selective predicate, or a `LIMIT` with a deterministic `ORDER BY`.
**Fine when:** a deliberate full aggregate (`SELECT COUNT(*) FROM t`), or a
small dimension table.

## SQL-08 — `JOIN` with no `ON`, or comma-separated `FROM`
**Costs:** cross product. Two 10k tables become 100M rows before any filter
runs. Often the join predicate got stranded in `WHERE`, which works but hides
the intent and defeats some planners.
**Fix:** explicit `JOIN ... ON`. If a cross join is intended, write
`CROSS JOIN` so the reader knows it was a choice.
**Fine when:** genuinely intentional `CROSS JOIN`.

## SQL-09 — `ORDER BY` with no `LIMIT`
**Costs:** sorts the entire result set. Past the sort-memory budget it spills to
disk — the usual cliff where a query goes from 200ms to 30s.
**Fix:** add `LIMIT`, or sort in the application if the client pages anyway. A
sort matching an existing index order is free; one that does not, is not.
**Fine when:** the caller truly needs every row ordered.

## SQL-10 — `DISTINCT`
**Costs:** a sort or hash over the whole result. More importantly it is usually
a *symptom*: duplicates appear because a join fanned out, and `DISTINCT` hides
that rather than fixing it — so you pay the fan-out *and* the dedup.
**Fix:** find the join that multiplies rows; aggregate it first, or use
`EXISTS` if you only needed existence.
**Fine when:** the duplicates are real data, not join artefacts.

## SQL-11 — `UNION` instead of `UNION ALL`
**Costs:** plain `UNION` deduplicates — a full sort/hash of both branches.
**Fix:** `UNION ALL` when the branches are already disjoint; mutually exclusive
`WHERE` clauses usually guarantee that.
**Fine when:** you actually need duplicates removed.

## SQL-12 — `OR` across different columns
**Costs:** `WHERE a = 1 OR b = 2` cannot use a single composite index; many
planners give up and scan. An index-merge is possible but fragile.
**Fix:** `UNION ALL` of two indexed branches, or `IN (...)` when the `OR`s are
all on one column.
**Fine when:** both sides are cheap, or the table is small.

## Indexes: what the scan cannot see

`scan_sql.py` reads text, not the catalogue. It cannot tell you an index is
missing — only that a predicate *would need* one. Phrase it that way:

> "This filter can only be served by an index on `orders(customer_id,
> created_at)`. Confirm with `EXPLAIN`."

Column order: equality first, then range, then `ORDER BY`. Never state an index
exists or is absent; route it through *What I could not verify*.
