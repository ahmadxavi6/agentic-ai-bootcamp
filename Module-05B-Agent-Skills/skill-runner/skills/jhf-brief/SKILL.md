---
name: jhf-brief
description: Produce a one-page, JHF-styled decision brief on a topic. Use when the user asks for a "brief", "one-pager", "exec summary" or "summary report" on something.
---

# Skill: JHF One-Page Brief

The house format for a decision brief. Four sections, under 400 words, no
throat-clearing. A busy reader should get the decision in 30 seconds.

## When to use this

Fires on: "brief", "one-pager", "exec summary", "summary report", "brief me on".

Does **not** fire on: general questions, code, maths, chit-chat. If someone asks
"what is RAG?" they want an explanation, not a brief. Answer normally.

## Steps

1. Call `read_resource("resources/brief-template.md")` to get the house skeleton.
2. Draft the content. Rules that are not negotiable:
   - **Summary** is 2–3 sentences. It states the conclusion, not the topic.
   - **Key Points** are 3–5 bullets. Each bullet carries one fact or number.
   - **Recommendation** is one sentence, and it must contain a verb. "Adopt X
     for Y" — not "X is worth considering."
   - **Risks** is 1–2 bullets. If there is genuinely no risk, write "None
     material." Never pad it.
3. Call `run_script("format_brief.py", <your draft>)`. The script enforces word
   count and heading order. It is the referee, not you.
4. If the script reports a problem, fix the draft and run it again.
5. Call `save_output("brief-<topic-slug>.md", <final text>)`.
6. Show the finished brief to the user.

## House style

- No "In today's fast-paced world." No "It is important to note that."
- Numbers beat adjectives. "Cuts review time 40%" beats "significantly faster."
- If you are not sure of a fact, mark it `[unverified]` rather than dropping it
  or inventing a number. A brief that lies is worse than a brief that is short.
