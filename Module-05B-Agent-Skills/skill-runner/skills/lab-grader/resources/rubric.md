# Lab Rubric — M5B Agent Skills

Five criteria. Each is PASS or FAIL, marked independently.

## 1. The skill is discoverable
`SKILL.md` has frontmatter with a `name` and a `description`. The description
says **when** to use the skill, in words a router could match against — not
just what it is. "Use when the user asks for X" beats "a skill for X".

## 2. The scope is narrow
The skill does one job. A skill called "handles documents" fails this. A skill
called "converts a meeting transcript into dated action items" passes.

## 3. Progressive disclosure is real
The full instructions are loaded **only** after the router matches. Evidence: a
transcript or screenshot showing the menu cost versus the loaded cost, or the
runner's token report.

## 4. It fires correctly — and stays dormant correctly
Two transcripts. One matching request where the skill loads and is used. One
unrelated request where it does **not** load. Both must be shown. A skill that
always fires is not a skill, it is a system prompt.

## 5. Determinism is pushed into code
Anything countable, checkable or formattable is done by a script or a template,
not by the model's goodwill. Evidence: a `scripts/` or `resources/` file that is
actually called in the transcript.
