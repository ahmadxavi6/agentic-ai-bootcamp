---
name: sql-explainer
description: Explain an unfamiliar SQL query in plain English, then recommend concrete performance fixes with the reason each one helps. Use when the user pastes a query and asks what it does, why it is slow, how to speed it up, or to review, tune or optimise SQL.
---

# Skill: SQL Explainer & Optimiser

Someone inherited a 60-line query with no comments and the author has left the
company. This skill turns that query into two things: a plain-English account of
what it does, and a short list of changes that will make it faster — each one
carrying the reason it helps.

## When to use this

Fires on: "what does this query do", "why is this query slow", "optimise this
SQL", "speed this up", "review this query", "explain this SQL", "this takes 40
seconds", "tune this".

Does **not** fire on:

- **Writing a new query from scratch** — "write me a query that returns monthly
  revenue". There is nothing to explain yet. Answer normally.
- **SQL syntax questions** — "what's the difference between LEFT and INNER
  JOIN". That is a teaching question, not an audit of a specific query.
- **Schema and data-model design** — "how should I structure this table".
- **Database operations** — backups, replication, connection pools, migrations.
- **ORM code with no SQL in it** — if you cannot see a query, this does not fire.

## Steps

1. Get the query text from the request. If the user gave a file path, call
   `read_resource` on it. **If there is no query, ask for it and stop** — do not
   invent one to demonstrate the skill.
2. Call `run_script("scan_sql.py", <the raw query>)`. Pass the query
   **verbatim** — including its comments and blank lines, exactly as the user
   gave it to you. If you strip anything first, every line number the scan
   returns will be offset from the file the user is looking at, and the report
   becomes useless to them.

   It returns a factual inventory (line count, tables, joins, subqueries) and a
   list of anti-pattern findings, each tagged with a code like `SQL-01` and a
   line number. **The scan is the only source of truth about what is in the
   query.** Do not report a pattern it did not find, and do not silently drop
   one it did.
3. Call `read_resource("resources/optimisation-checklist.md")`. That file holds
   the *why* for every `SQL-xx` code the scan emitted — the cost mechanism, the
   fix, and the cases where the pattern is actually fine and should be left
   alone.
4. Write the report with exactly these four headings, in this order:

   - `## What this query does` — one plain-language paragraph, then a numbered
     walk-through in *execution* order (FROM and JOINs first, then WHERE, then
     GROUP BY, then SELECT, then ORDER BY) — not the order the text is written
     in. That reordering is most of the value; it is how the database reads it.
   - `## Findings` — a markdown table with exactly these columns:
     `| Line | Pattern | Why it costs | Fix |`
     One row per scan finding. Write **Pattern** in plain words with the code in
     brackets — `SELECT * (SQL-01)`, not a bare `SQL-01`; the person reading
     this does not have the checklist open. **"Why it costs" must name the
     mechanism** — the extra rows read, the index that cannot be used, the sort
     that gets added. "It is faster" and "best practice" are not mechanisms.
   - `## Rewritten query` — the improved SQL in a fenced block. Preserve the
     original result semantics. If a fix would change the rows returned, do not
     apply it; put it in the next section instead.
   - `## What I could not verify` — at least one honest bullet. Indexes, row
     counts, data distribution and cardinality are invisible from the query
     text. Every index recommendation belongs here as an assumption to check
     with `EXPLAIN`, not in the rewritten query as a fact.
5. Call `run_script("check_report.py", <your draft>)`. It enforces the heading
   set, the table shape, and that every finding row actually gives a reason. It
   is the referee, not you.
6. If it reports a problem, fix the draft and run it again.
7. Call `save_output("sql-review-<short-slug>.md", <final text>)`, then show the
   report to the user.

## Rules

- **A pattern found is not a problem proven.** `scan_sql.py` is a lexical
  scanner with no schema access. If a finding does not actually matter for this
  query, say so in the row and explain why — a `SELECT *` over a five-row lookup
  table is not worth a code change. Suppressing a real finding is a failure;
  so is inflating a harmless one.
- **Never claim an index exists, or that one is missing.** You cannot see them.
  Write "this filter can only use an index on `orders(customer_id, created_at)`
  — confirm with `EXPLAIN`" and put it under *What I could not verify*.
- **Never invent a row count or a runtime.** No "this scans 4 million rows"
  unless the user gave you that number.
- **Explain why, not just what.** A row that says "replace `SELECT *` with
  explicit columns" and stops has failed this skill's one job. The reason is the
  deliverable.
- Keep the rewritten query readable — the next person to inherit it is also
  going to have no comments to work from. Alias consistently and add a one-line
  comment above any non-obvious clause.
