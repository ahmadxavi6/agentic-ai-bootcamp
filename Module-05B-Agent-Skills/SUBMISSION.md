# M5B Submission — Scenario 11: SQL Explainer & Optimiser

**Shape:** 📚 instructions + knowledge  ·  **Level:** 🟨 some work

**The problem.** A 60-line query, no comments, and the author has left the company.
**What I built.** Query in → plain-English explanation, then concrete improvements.
**Script / resource.** A checklist resource: SELECT *, missing indexes, N+1, implicit casts, functions on indexed columns.
**Done when.** It explains why each change helps, not just what to change.

---

## My skill

```
skills/sql-explainer/
  SKILL.md                              the playbook (~1,243 tokens, loaded only on match)
  resources/
    optimisation-checklist.md           12 anti-patterns: cost mechanism, fix, when it's fine
    sample-query.sql                    the inherited 24-line query, for testing
  scripts/
    scan_sql.py                         LOCATES the patterns + line numbers (no reasoning)
    check_report.py                     REFEREE: fails any finding that doesn't say why
```

The checklist is the knowledge the scenario asked for. I added two scripts because
the checklist alone leaves the "done when" unenforced — a prompt can *ask* for a
reason, only code can *reject* a draft that doesn't give one.

**The division of labour is the design:**

| Question | Answered by |
|---|---|
| *Where* is the pattern, how many are there? | `scan_sql.py` — regex + line numbers |
| *Why* does it cost? | `optimisation-checklist.md` — the knowledge |
| Does it matter for *this* query? | the model — the only real judgement call |
| Did it actually explain the why? | `check_report.py` — the gate |

The checklist is keyed `SQL-01` … `SQL-12`, and the scanner emits those same codes.
The model cannot write a Findings row without looking the code up, and cannot
invent a code the scanner didn't emit.

---

## Transcript 1 — it fires

Request: the inherited query pasted in, with *"This ran in 4 minutes and now takes 40.
What does it actually do, and how do I speed it up?"*

```
====================================================================
REQUEST  This ran in 4 minutes and now takes 40. What does it actually do, and how do I speed it up?

-- Inherited from a contractor who left in March. No comments, no ticket.
-- Runs nightly, used to take 4 minutes, now takes 40.
SELECT DISTINCT
    c.*,
    (SELECT SUM(oi.quantity * oi.unit_price)
       FROM order_items oi
       JOIN orders o2 ON o2.order_id = oi.order_id
      WHERE o2.customer_id = c.customer_id) AS lifetime_value,
    ... (24 lines total)
SKILLS   4 on disk: jhf-brief, lab-grader, repo-onboarder, sql-explainer
ROUTED   sql-explainer
====================================================================
  -> run_script({'script_name': 'scan_sql.py', 'stdin_text': "-- Inherited f...)
  -> read_resource({'relative_path': 'resources/optimisation-checklist.md'}...)
  -> run_script({'script_name': 'check_report.py', 'stdin_text': "## What th...)
  -> save_output({'filename': 'sql-review-customers-query.md', 'content': "##...)
```

All four tools fire in order: **locate → look up the why → get refereed → save.**

`scan_sql.py` found 9 of the 12 patterns, with line numbers:

```
=== QUERY INVENTORY (facts — do not contradict these) ===
  lines ................ 24
  tables referenced .... 5: customer_segments, customers, order_items, orders, refunds
  joins ................ 4 (ON clauses: 4)
  subqueries ........... 3
  has WHERE ............ yes
  has LIMIT ............ NO

=== FINDINGS: 9 pattern(s) located ===
  SQL-01  line 4     SELECT * — every column is fetched, including ones never used
  SQL-02  line 17, 18  function on a filtered/joined column (lower, year) — non-sargable
  SQL-03  line 18    LIKE with a leading % — no index prefix to seek on
  SQL-04  line 19    quoted literal compared to a numeric-looking column
  SQL-05  line 5, 9  subquery in the SELECT list — runs once per output row
  SQL-06  line 21    NOT IN — returns zero rows if the subquery yields NULL
  SQL-09  line 24    ORDER BY with no LIMIT — sorts the whole result set
  SQL-10  line 3     DISTINCT — check whether duplicates come from a join fan-out
  SQL-12  line 20    OR across columns — a composite index cannot serve both sides
```

The saved report (`output/sql-review-customers-query.md`, 4,098 bytes) — Findings extract:

| Line | Pattern | Why it costs | Fix |
|---|---|---|---|
| 4 | SELECT * (SQL-01) | Fetching all columns can transfer unnecessary data and block covering indexes. | Specify only the columns needed. |
| 17, 18 | Function on a filtered/joined column (SQL-02) | Using `YEAR(o.created_at)` prevents index seeking, leading to full table scans. | `WHERE o.created_at >= '2024-01-01' AND o.created_at < '2025-01-01'` |
| 5, 9 | Subquery in the SELECT list (SQL-05) | Each subquery runs for every row returned, leading to N+1 query execution. | `LEFT JOIN` a pre-aggregated table instead. |
| 21 | NOT IN / IN (SELECT ...) (SQL-06) | `NOT IN` can return zero rows if the subquery yields NULL, and it blocks optimizations. | Replace with `NOT EXISTS`. |

Every line number matches the scan. Every row names a mechanism, not a verdict.
The report closes with *What I could not verify* — indexes, row counts, and
`EXPLAIN` plans — because none of those are visible in query text.

---

## Transcript 2 — it stays dormant

The hard dormancy test: a question that is *about SQL* and *contains the word JOIN*,
but is not an audit of a specific query.

```
====================================================================
REQUEST  What is the difference between a LEFT JOIN and an INNER JOIN?
SKILLS   4 on disk: jhf-brief, lab-grader, repo-onboarder, sql-explainer
ROUTED   NO_SKILL — answering directly
====================================================================

ANSWER
The difference between a LEFT JOIN and an INNER JOIN in SQL pertains to how they
handle the rows from the tables being joined...

--------------------------------------------------------------------
PROGRESSIVE DISCLOSURE — what it actually cost
  skills on disk .............. 4
  menu shown to the router .... ~302 tokens
  if we had loaded ALL of them. ~2,724 tokens
  we actually loaded .......... ~0 tokens (nothing)
  SAVED ....................... ~2,724 tokens
--------------------------------------------------------------------
```

Zero tokens loaded, no tools called. The `Does NOT fire on` list in `SKILL.md`
names this case explicitly: *"SQL syntax questions — that is a teaching question,
not an audit of a specific query."*

---

## Token report from skill_runner.py

**Fires** (query pasted in):

```
PROGRESSIVE DISCLOSURE — what it actually cost
  skills on disk .............. 4
  menu shown to the router .... ~302 tokens
  if we had loaded ALL of them. ~2,724 tokens
  we actually loaded .......... ~1,243 tokens (sql-explainer)
  SAVED ....................... ~1,481 tokens

  trace:
    run_script     {'script_name': 'scan_sql.py', 'stdin_text': "-- Inherited from a cont
    read_resource  {'relative_path': 'resources/optimisation-checklist.md'}
    run_script     {'script_name': 'check_report.py', 'stdin_text': "## What this query d
    save_output    {'filename': 'sql-review-customers-query.md', 'content': "## What this
```

**Stays dormant** (JOIN syntax question): `~0 tokens loaded, ~2,724 saved`.

The number that matters most isn't in the report: the 12-entry checklist is
**5,946 characters** — roughly 1,500 tokens of knowledge that is read *only* on
the third step of a matched request, and never enters context otherwise. The
router decides on 302 tokens.

---

## Three sentences

1. **Why this is a skill and not a prompt:** it is dormant by default — the router
   spends 302 tokens on a menu, and the 1,243-token playbook plus ~1,500 tokens of
   checklist stay on disk until someone actually pastes a query, which a system
   prompt cannot do; a prompt also cannot carry a scanner and a referee that
   *execute*.
2. **Its narrow scope is:** explaining and optimising **one SQL query that already
   exists** — not writing new SQL, not teaching JOIN semantics, not schema design
   or database operations, which is exactly why the `LEFT JOIN` question left it
   dormant.
3. **What I pushed into code instead of the model:** locating all 12 anti-patterns
   with line numbers and counting tables/joins/subqueries (`scan_sql.py` — that is
   regex and `len()`, not reasoning), and enforcing the scenario's "done when" —
   `check_report.py` **fails** any Findings row whose *Why it costs* cell is under
   six words or leans on a stock phrase like "best practice" or "more efficient",
   so "explains why" is a gate rather than a hope.

---

## Notes on building it

Three bugs the lab caught that are worth recording:

- **SQL-01 initially missed `SELECT DISTINCT\n    c.*`.** My first check was
  line-by-line, and real queries put `SELECT` and the star on different lines.
  Fixed by matching across the whole statement and mapping character offsets back
  to line numbers — anchoring on the `SELECT` keyword is also what keeps `COUNT(*)`
  and `qty * price` out of the results.
- **The model stripped the comments before calling the scanner**, so every line
  number in the first report was offset by 2 from the file the user was reading.
  Fixed with an explicit instruction to pass the query *verbatim*, and it held on
  the re-run.
- **The model first "fixed" `LIKE '%@acme.com'` by deleting the `%`** — which
  silently changes the result set. The checklist now says so in bold, because a
  suffix match has no index-friendly rewrite without a trigram or reversed-column
  index.

A model-quality note: `openai/gpt-4.1-nano` routed correctly but skipped
`read_resource` and the referee entirely, and dropped a table column.
`openai/gpt-4o-mini` followed all seven steps. The transcripts above are
`gpt-4o-mini`.
