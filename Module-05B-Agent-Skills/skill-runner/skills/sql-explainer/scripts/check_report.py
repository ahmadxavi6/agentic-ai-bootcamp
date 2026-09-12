"""check_report.py — the referee for the sql-explainer skill.

The scenario's "done when" is: *it explains why each change helps, not just
what to change.* That is the one thing worth enforcing, and a prompt cannot
enforce it — a prompt can only ask. So this script parses the Findings table
and fails the draft if any row's "Why it costs" cell is empty, one word, or a
stock phrase with no mechanism in it.

Also checks the four headings exist and are in order, and that *What I could
not verify* is not left as decoration — because the tempting failure mode for
this skill is inventing an index that is not there.

Reads the draft on stdin, prints a verdict. Unlike jhf-brief's referee this
does NOT echo the draft back: SQL reports run long and the runner truncates
tool results at 6000 characters, which would eat the verdict.
"""

from __future__ import annotations

import re
import sys

REQUIRED = [
    "## What this query does",
    "## Findings",
    "## Rewritten query",
    "## What I could not verify",
]

EXPECTED_COLUMNS = ["line", "pattern", "why it costs", "fix"]

# Phrases that look like a reason but name no mechanism. A real "why" says what
# the engine has to do differently — rows scanned, index not seekable, a sort
# added. These say "trust me".
HAND_WAVES = [
    "best practice",
    "more efficient",
    "it is faster",
    "it's faster",
    "improves performance",
    "better performance",
    "for performance reasons",
    "generally faster",
    "is slow",
    "bad practice",
    "not optimal",
    "inefficient",
    "cleaner",
]

MIN_WHY_WORDS = 6


def table_rows(text: str) -> list[list[str]]:
    """Pull the Findings table out as a list of cell-lists.

    Skips the header row and the |---|---| separator. Returns [] if there is
    no table at all, which the caller treats differently from a bad table.
    """
    section = text.split("## Findings", 1)
    if len(section) < 2:
        return []
    body = re.split(r"\n##\s", section[1])[0]

    rows: list[list[str]] = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        if re.fullmatch(r"\|[\s:|-]+\|", line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        rows.append(cells)
    return rows


def check(text: str) -> list[str]:
    problems: list[str] = []

    missing = [h for h in REQUIRED if h not in text]
    if missing:
        problems.append("MISSING HEADINGS: " + ", ".join(missing))

    present = [h for h in REQUIRED if h in text]
    positions = [text.find(h) for h in present]
    if positions != sorted(positions):
        problems.append("HEADINGS OUT OF ORDER: expected " + " -> ".join(REQUIRED))

    rows = table_rows(text)
    if not rows:
        problems.append(
            "NO FINDINGS TABLE: '## Findings' must contain a markdown table "
            "| Line | Pattern | Why it costs | Fix |"
        )
    else:
        header = [c.lower() for c in rows[0]]
        if header[: len(EXPECTED_COLUMNS)] != EXPECTED_COLUMNS:
            problems.append(
                "WRONG COLUMNS: got " + " | ".join(rows[0])
                + " — expected Line | Pattern | Why it costs | Fix"
            )
        data = rows[1:]
        if not data:
            problems.append(
                "FINDINGS TABLE IS EMPTY: if the scan found nothing, write one row "
                "saying so — do not ship an empty table."
            )
        for i, cells in enumerate(data, start=1):
            label = f"row {i}"
            if len(cells) < 4:
                problems.append(f"{label}: has {len(cells)} cells, needs 4.")
                continue

            line_cell, pattern_cell, why, fix = cells[0], cells[1], cells[2], cells[3]

            if not re.search(r"\d", line_cell):
                problems.append(
                    f"{label}: Line cell '{line_cell}' has no line number — "
                    "every finding must point at the query."
                )
            if not pattern_cell:
                problems.append(f"{label}: Pattern cell is empty.")
            elif re.fullmatch(r"[`\s]*SQL-\d+[`\s]*", pattern_cell, re.IGNORECASE):
                # A bare checklist code is a reference, not a description. The
                # reader does not have the checklist open.
                problems.append(
                    f"{label}: Pattern cell is just '{pattern_cell}' — name the pattern "
                    "in plain words with the code in brackets, e.g. 'SELECT * (SQL-01)'."
                )

            why_words = len(why.split())
            if why_words < MIN_WHY_WORDS:
                problems.append(
                    f"{label}: 'Why it costs' is {why_words} word(s) — needs a real "
                    f"mechanism (>= {MIN_WHY_WORDS} words). This is the deliverable, not a label."
                )
            else:
                lowered = why.lower()
                for phrase in HAND_WAVES:
                    if phrase in lowered:
                        problems.append(
                            f"{label}: 'Why it costs' says '{phrase}' — that names no "
                            "mechanism. Say what the engine must do differently."
                        )
                        break
            if not fix:
                problems.append(f"{label}: Fix cell is empty.")

    if "## What I could not verify" in text:
        tail = text.split("## What I could not verify", 1)[1]
        tail = re.split(r"\n##\s", tail)[0]
        bullets = [ln for ln in tail.splitlines() if ln.strip().startswith(("-", "*"))]
        if not bullets:
            problems.append(
                "'What I could not verify' has no bullets — indexes, row counts and "
                "data distribution are always invisible from query text. Name at least one."
            )

    if "## Rewritten query" in text:
        tail = text.split("## Rewritten query", 1)[1]
        tail = re.split(r"\n##\s", tail)[0]
        if "```" not in tail:
            problems.append("'Rewritten query' has no fenced code block.")

    return problems


def main() -> None:
    text = sys.stdin.read()
    if not text.strip():
        print("FAIL — nothing received on stdin.")
        return

    problems = check(text)
    if problems:
        print(f"FAIL — {len(problems)} problem(s). Fix these and run me again:")
        for p in problems:
            print(f"  - {p}")
        return

    rows = max(0, len(table_rows(text)) - 1)
    print(f"PASS — 4 headings in order, {rows} finding(s), every row gives a mechanism.")


if __name__ == "__main__":
    main()
