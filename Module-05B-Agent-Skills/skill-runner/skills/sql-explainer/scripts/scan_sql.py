"""scan_sql.py — the locator for the sql-explainer skill.

DIVISION OF LABOUR
------------------
This script answers "WHERE is the pattern, and how many are there."
resources/optimisation-checklist.md answers "WHY does it cost."
The model answers "does it matter for THIS query."

Finding a `SELECT *` is not reasoning — it is a regex and a line number. Asking
a model to do it means it sometimes misses one, and always sounds equally
confident either way. Counting joins is `len()`. So all of that lives here,
where the answer is the same every run and cannot be argued with.

What this deliberately does NOT do: decide severity, guess at indexes, or
estimate rows. It has no schema, no statistics and no parser. It emits codes;
the model must look each one up and justify it against the actual query.

Reads SQL on stdin, prints an inventory plus SQL-xx findings with line numbers.
"""

from __future__ import annotations

import re
import sys

KEYWORDS_ENDING_WHERE = r"group\s+by|order\s+by|having|limit|window|union|offset|fetch\s+first"

# Functions that kill sargability when wrapped around a column (SQL-02).
NON_SARGABLE_FNS = (
    "upper|lower|date|year|month|day|cast|convert|trunc|date_trunc|"
    "substr|substring|left|right|coalesce|ifnull|nvl|to_char|to_date|"
    "datediff|dateadd|floor|ceil|round|abs|concat|trim|replace"
)

# Column names that are almost certainly numeric — used for the implicit-cast
# check (SQL-04). Deliberately conservative: a false positive is a wasted row
# in the report, so we only flag names that are strongly numeric by convention.
NUMERIC_ISH = (
    r"(?:\w*_)?id|qty|quantity|amount|price|total|count|num|number|"
    r"age|year|month|day|size|length|width|height|weight|score|rank|level"
)

BOUNDED = r"\b(?:limit|top|fetch\s+first)\b"


def strip_comments(lines: list[str]) -> list[str]:
    """Blank out comments while preserving line numbering.

    Line numbers are the whole point of this script's output, so we never
    delete a line — we only empty it. Handles `--`, `#` and `/* */`.

    Known limit: a `--` or `#` inside a string literal ends the line early.
    Stripping comments correctly before knowing where literals are is a
    chicken-and-egg problem that needs a real lexer; the failure mode here is
    a missed finding, not a wrong one.
    """
    out: list[str] = []
    in_block = False
    for line in lines:
        buf: list[str] = []
        i = 0
        while i < len(line):
            two = line[i : i + 2]
            if in_block:
                if two == "*/":
                    in_block = False
                    i += 2
                else:
                    i += 1
                continue
            if two == "/*":
                in_block = True
                i += 2
                continue
            if two == "--" or line[i] == "#":
                break
            buf.append(line[i])
            i += 1
        out.append("".join(buf))
    return out


def blank_strings(text: str) -> str:
    """Replace string-literal contents with spaces of equal length.

    Keeps every offset and line number intact so later checks stay aligned,
    and stops a literal like 'JOIN ME' from firing a structural check. Run
    AFTER any check that needs to read literal text (SQL-03, SQL-04).
    """
    return re.sub(r"'([^']*)'", lambda m: "'" + (" " * len(m.group(1))) + "'", text)


def find_lines(lines: list[str], pattern: str) -> list[int]:
    rx = re.compile(pattern, re.IGNORECASE)
    return [i + 1 for i, line in enumerate(lines) if rx.search(line)]


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def where_regions(sql: str) -> str:
    """Concatenate every WHERE / ON / HAVING region.

    A function call in the SELECT list is harmless; the same call in a WHERE or
    ON clause is what destroys an index seek. So the sargability checks look
    only here, not at the whole statement.
    """
    regions: list[str] = []
    for m in re.finditer(
        r"\b(?:where|having)\b(.*?)(?=\b(?:" + KEYWORDS_ENDING_WHERE + r")\b|;|$)",
        sql,
        re.IGNORECASE | re.DOTALL,
    ):
        regions.append(m.group(1))
    for m in re.finditer(
        r"\bon\b(.*?)(?=\b(?:where|inner|left|right|full|cross|join|group\s+by|"
        r"order\s+by|having|limit)\b|;|$)",
        sql,
        re.IGNORECASE | re.DOTALL,
    ):
        regions.append(m.group(1))
    return "\n".join(regions)


def select_list(sql: str) -> tuple[str, int]:
    """Return (text, absolute_offset) for the outermost SELECT list.

    Tracks paren depth so a nested `(SELECT ... FROM ...)` does not end the
    outer list early — that nesting is exactly what SQL-05 looks for.
    """
    m = re.search(r"\bselect\b", sql, re.IGNORECASE)
    if not m:
        return "", 0
    start = m.end()
    depth = 0
    for i in range(start, len(sql)):
        ch = sql[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and sql[i : i + 4].lower() == "from":
            before_ok = i == 0 or not (sql[i - 1].isalnum() or sql[i - 1] == "_")
            after_ok = not (sql[i + 4 : i + 5].isalnum() or sql[i + 4 : i + 5] == "_")
            if before_ok and after_ok:
                return sql[start:i], start
    return sql[start:], start


def scan(raw: str) -> tuple[list[str], list[tuple[str, list[int], str]]]:
    lines = strip_comments(raw.splitlines())
    sql_literal = "\n".join(lines)       # comments gone, literals intact
    sql = blank_strings(sql_literal)      # literals neutralised too
    safe_lines = sql.splitlines()

    wr = where_regions(sql)
    sel, sel_offset = select_list(sql)
    lowered = sql.lower()

    has_where = bool(re.search(r"\bwhere\b", lowered))
    has_limit = bool(re.search(BOUNDED, lowered))

    findings: list[tuple[str, list[int], str]] = []

    def add(code: str, hits: list[int], detail: str) -> None:
        if hits:
            findings.append((code, sorted(set(hits)), detail))

    # SQL-01 — SELECT * / SELECT alias.*
    #
    # Matched across the whole statement rather than line-by-line: a real query
    # writes `SELECT DISTINCT` on one line and `c.*` on the next, and a
    # per-line regex silently misses it. Anchoring on the SELECT keyword is
    # also what keeps `COUNT(*)` and the `*` in `qty * unit_price` out — both
    # lack a preceding SELECT.
    add(
        "SQL-01",
        [
            line_of(sql, m.start(1))
            for m in re.finditer(
                r"\bselect\b(?:\s+distinct\b)?\s*((?:[a-z_]\w*\.)?\*)", sql, re.IGNORECASE
            )
        ],
        "SELECT * — every column is fetched, including ones never used",
    )

    # SQL-02 — function wrapped around a column inside WHERE/ON/HAVING
    fn_rx = re.compile(
        r"\b(" + NON_SARGABLE_FNS + r")\s*\(\s*(?:[a-z_]\w*\.)?[a-z_]\w*\s*[,)]",
        re.IGNORECASE,
    )
    fn_names = sorted({m.group(1).lower() for m in fn_rx.finditer(wr)})
    if fn_names:
        alt = "|".join(re.escape(f) for f in fn_names)
        add(
            "SQL-02",
            find_lines(safe_lines, r"\b(" + alt + r")\s*\("),
            f"function on a filtered/joined column ({', '.join(fn_names)}) — non-sargable",
        )

    # SQL-03 — leading-wildcard LIKE (needs the raw literal, so scan `lines`)
    add(
        "SQL-03",
        find_lines(lines, r"\b(?:i?like|rlike)\s+'\s*%"),
        "LIKE with a leading % — no index prefix to seek on",
    )

    # SQL-04 — implicit cast: numeric-looking column compared to a quoted literal
    ops = r"(?:=|<>|!=|<=|>=|<|>)"
    cast_hits = find_lines(
        lines, r"\b(?:\w+\.)?(?:" + NUMERIC_ISH + r")\s*" + ops + r"\s*'"
    )
    cast_hits += find_lines(lines, r"'\s*\d+\s*'\s*" + ops)
    add(
        "SQL-04",
        cast_hits,
        "quoted literal compared to a numeric-looking column — possible implicit cast",
    )

    # SQL-05 — scalar subquery in the SELECT list (N+1 inside the database).
    # Map offsets inside the select list back to real line numbers, so we never
    # blame a subquery that lives somewhere harmless.
    sel_subqueries = [
        line_of(sql, sel_offset + m.start())
        for m in re.finditer(r"\(\s*select\b", sel, re.IGNORECASE)
    ]
    add(
        "SQL-05",
        sel_subqueries,
        "subquery in the SELECT list — runs once per output row unless decorrelated",
    )

    # SQL-06 — NOT IN (a correctness risk, not just speed) and IN (SELECT ...)
    add(
        "SQL-06",
        find_lines(safe_lines, r"\bnot\s+in\s*\(")
        + find_lines(safe_lines, r"\bin\s*\(\s*select\b"),
        "NOT IN / IN (SELECT ...) — NOT IN returns zero rows if the subquery yields NULL",
    )

    # SQL-07 — unbounded: a SELECT with no WHERE and no LIMIT
    if re.search(r"\bfrom\b", lowered) and not has_where and not has_limit:
        add("SQL-07", [1], "no WHERE and no LIMIT — unbounded scan and unbounded result set")

    # SQL-08 — JOIN without ON, or comma-separated FROM
    joins = len(re.findall(r"\bjoin\b", lowered))
    explicit_cross = len(re.findall(r"\b(?:cross|natural)\s+join\b", lowered))
    ons = len(re.findall(r"\bon\b", lowered))
    if joins - explicit_cross > ons:
        add("SQL-08", [1], f"{joins} JOIN(s) but only {ons} ON clause(s) — cartesian risk")
    add(
        "SQL-08",
        find_lines(safe_lines, r"\bfrom\b\s+[a-z_]\w*(?:\s+(?:as\s+)?[a-z_]\w*)?\s*,"),
        "comma-separated FROM — implicit cross join",
    )

    # SQL-09 — ORDER BY with no LIMIT
    if re.search(r"\border\s+by\b", lowered) and not has_limit:
        add(
            "SQL-09",
            find_lines(safe_lines, r"\border\s+by\b"),
            "ORDER BY with no LIMIT — sorts the whole result set, spills to disk when large",
        )

    # SQL-10 — DISTINCT, usually a join-fan-out bandaid.
    # Offset-based for the same reason as SQL-01: `SELECT` and `DISTINCT` are
    # routinely on different lines.
    add(
        "SQL-10",
        [
            line_of(sql, m.start())
            for m in re.finditer(
                r"\bselect\s+distinct\b|\bcount\s*\(\s*distinct\b", sql, re.IGNORECASE
            )
        ],
        "DISTINCT — check whether the duplicates come from a join fan-out",
    )

    # SQL-11 — UNION where UNION ALL would do
    add(
        "SQL-11",
        find_lines(safe_lines, r"\bunion\b(?!\s+all)"),
        "UNION without ALL — deduplicates, which sorts both branches",
    )

    # SQL-12 — OR across different columns in a WHERE region
    or_cols = re.findall(r"([a-z_]\w*(?:\.\w+)?)\s*(?:=|<>|!=|<=|>=|<|>|like)", wr, re.IGNORECASE)
    if re.search(r"\bor\b", wr, re.IGNORECASE) and len({c.lower() for c in or_cols}) > 1:
        add(
            "SQL-12",
            find_lines(safe_lines, r"\bor\b"),
            "OR across columns — a single composite index cannot serve both sides",
        )

    # ---- inventory: the countable facts -----------------------------------
    tables = sorted(set(re.findall(r"\b(?:from|join)\s+([a-z_][\w.]*)", lowered)))
    cte_pairs = re.findall(r"\bwith\s+([a-z_]\w*)\s+as\s*\(|,\s*([a-z_]\w*)\s+as\s*\(", lowered)
    cte_names = sorted({a or b for a, b in cte_pairs if (a or b)})
    subqueries = len(re.findall(r"\(\s*select\b", lowered))
    agg = sorted(
        {
            m.lower()
            for m in re.findall(r"\b(count|sum|avg|min|max|group_concat|string_agg)\s*\(", lowered)
        }
    )
    verb_match = re.match(r"\s*(\w+)", sql_literal)
    verb = verb_match.group(1).upper() if verb_match else "?"

    inventory = [
        f"lines ................ {len(lines)}",
        f"statement ............ {verb}",
        f"tables referenced .... {len(tables)}: {', '.join(tables) or '(none)'}",
        f"joins ................ {joins} (ON clauses: {ons})",
        f"subqueries ........... {subqueries}",
        f"CTEs ................. {len(cte_names)}: {', '.join(cte_names) or '(none)'}",
        f"aggregates ........... {', '.join(agg) or '(none)'}",
        f"has WHERE ............ {'yes' if has_where else 'NO'}",
        f"has LIMIT ............ {'yes' if has_limit else 'NO'}",
    ]
    return inventory, findings


def main() -> None:
    raw = sys.stdin.read()
    if not raw.strip():
        print("ERROR: no SQL received on stdin. Ask the user for the query.")
        return

    inventory, findings = scan(raw)

    print("=== QUERY INVENTORY (facts — do not contradict these) ===")
    for row in inventory:
        print(f"  {row}")

    print(f"\n=== FINDINGS: {len(findings)} pattern(s) located ===")
    if not findings:
        print("  none of the 12 checklist patterns matched.")
        print("  Say so plainly. Do not invent a finding to fill the table.")
    else:
        for code, hits, detail in findings:
            shown = ", ".join(str(h) for h in hits[:8])
            more = f" (+{len(hits) - 8} more)" if len(hits) > 8 else ""
            print(f"  {code}  line {shown}{more}")
            print(f"          {detail}")

    print("\n=== HOW TO USE THIS ===")
    print("  1. read_resource('resources/optimisation-checklist.md') for the WHY of each code.")
    print("  2. One Findings row per code above. Do not add codes that are not listed.")
    print("  3. This is a LEXICAL scan: no schema, no indexes, no row counts, no parser.")
    print("     A located pattern may be harmless here — say so and explain why.")


if __name__ == "__main__":
    main()
