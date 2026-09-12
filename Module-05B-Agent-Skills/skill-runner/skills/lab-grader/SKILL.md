---
name: lab-grader
description: Grade a student lab submission against the bootcamp rubric, one independent examiner per criterion. Use when the user asks to grade, mark, assess, score or review a submission against a rubric.
---

# Skill: Lab Grader

Grades a submission against the rubric — and does it by **starting other
agents**, one per criterion.

## Why this skill spawns agents instead of just thinking

You could paste the whole rubric and the whole submission into one prompt and
ask for five scores. It half-works, and it fails in a specific way: the model
reads criterion 1, forms an overall impression, and then marks criteria 2–5 to
match it. Graders call this the **halo effect**. Humans do it too. It is why
exam boards mark question-by-question, not script-by-script.

So this skill does what an exam board does:

    lab-grader (skill)
        |
        +-- sub-agent 1  ->  sees ONLY criterion 1 + the submission
        +-- sub-agent 2  ->  sees ONLY criterion 2 + the submission
        +-- sub-agent 3  ->  sees ONLY criterion 3 + the submission
        |
        +-- parent aggregates the five verdicts into one report

Each examiner has a **fresh context window**. It cannot be anchored by a mark
it never saw. The parent never sees the examiners' reasoning — only their
verdicts — so the parent's context stays small no matter how long the
submission is.

**That is the closing idea of this module: a skill is not only instructions.
A skill can be an orchestrator.**

## Steps

1. Call `read_resource("resources/rubric.md")` to load the five criteria.
2. Get the submission text from the user's request. If they gave a path, call
   `read_resource` on it. If you have no submission, ask for it and stop.
3. For **each** of the five criteria, call `run_subagent` with:
   - `role`: "You are an exam marker. You assess ONE criterion only. You have
     not seen any other criterion and must not speculate about them. Reply in
     exactly three lines: VERDICT: PASS or FAIL / EVIDENCE: a direct quote from
     the submission / FIX: one concrete action, or NONE."
   - `task`: that single criterion, then the full submission.

   Five separate calls. Do not batch them — batching rebuilds the exact halo
   effect this design exists to prevent.
4. Aggregate into a table: Criterion | Verdict | Evidence | Fix.
5. State the overall result: **PASS** needs 4 of 5. Otherwise **REVISE**.
6. Write two sentences of encouragement that name something specific the
   student actually did. Generic praise is worse than none.
7. Call `save_output("grade-<student>.md", <the report>)`.

## Rules

- Never invent a quote. If a criterion has no supporting evidence in the
  submission, that is a FAIL with `EVIDENCE: none found`.
- Never soften a FAIL into a PASS because the rest was good. That is the halo
  effect arriving through the back door.
