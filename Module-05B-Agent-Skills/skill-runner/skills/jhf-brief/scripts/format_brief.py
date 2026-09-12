"""format_brief.py — the referee for the jhf-brief skill.

Deterministic checks do not belong in the model. Counting words is not a
reasoning task; it is a `len()`. Every check you move OUT of the prompt and
INTO a script is a check that can no longer be argued with, forgotten, or
hallucinated as passed.

Reads the draft on stdin, prints a verdict plus the text.
"""

import sys

MAX_WORDS = 400
REQUIRED = ["## Summary", "## Key Points", "## Risks", "## Recommendation"]
BANNED = [
    "in today's fast-paced",
    "it is important to note",
    "in conclusion",
    "delve into",
    "landscape of",
]


def check(text: str) -> list[str]:
    problems = []

    words = len(text.split())
    if words > MAX_WORDS:
        problems.append(f"TOO LONG: {words} words (max {MAX_WORDS}). Cut {words - MAX_WORDS}.")

    missing = [h for h in REQUIRED if h not in text]
    if missing:
        problems.append("MISSING HEADINGS: " + ", ".join(missing))

    positions = [text.find(h) for h in REQUIRED if h in text]
    if positions != sorted(positions):
        problems.append("HEADINGS OUT OF ORDER: " + " -> ".join(REQUIRED))

    lowered = text.lower()
    for phrase in BANNED:
        if phrase in lowered:
            problems.append(f"BANNED PHRASE: '{phrase}' — rewrite that sentence.")

    if "## Recommendation" in text:
        rec = text.split("## Recommendation", 1)[1].strip()
        if len(rec.split()) < 4:
            problems.append("RECOMMENDATION TOO THIN: needs a real sentence with a verb.")

    return problems


def main() -> None:
    text = sys.stdin.read()
    problems = check(text)
    if problems:
        print("FAIL — fix these and resubmit:")
        for p in problems:
            print(f"  - {p}")
    else:
        print(f"PASS — {len(text.split())} words, all headings present and in order.")
    print("\n--- draft as received ---")
    print(text)


if __name__ == "__main__":
    main()
