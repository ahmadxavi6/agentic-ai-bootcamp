---
name: repo-onboarder
description: Explain an unfamiliar code repository to a newcomer — what it does, how to run it, where to start reading. Use when the user asks to understand, explore, onboard onto, or get oriented in a codebase or folder.
---

# Skill: Repo Onboarder

Point this at a folder you have never seen. It produces the page you wish every
repo had: what this is, how to run it, and the three files to read first.

## When to use this

Fires on: "explain this repo", "how do I get started with", "what is this
codebase", "onboard me onto", "where do I start reading".

Does **not** fire on: writing new code, fixing a bug, reviewing a diff.

## Steps

1. Work out the target folder from the request. If the user gave no path, use
   `.` and say so.
2. Call `run_script("scan_repo.py", <the path>)`. It returns a factual inventory:
   file tree, languages, entry points, dependency files, sizes.
   **Do not guess any of this.** The script is the only source of truth about
   what is on disk.
3. Read the inventory. If a README or requirements file was found, its contents
   are included — use them.
4. Write the onboarding note with exactly these sections:

   - **What this is** — one paragraph, plain language, no jargon.
   - **How to run it** — real commands, taken from what the scan found. If the
     scan found no way to run it, say "No entry point found" rather than
     inventing `npm start`.
   - **Read these first** — exactly 3 files, each with one line on why.
   - **Questions I could not answer from the code** — be honest. This section
     is the most useful one and it is the one models usually skip.

5. Call `save_output("onboarding-<repo-name>.md", <the note>)`.

## The rule that matters

Every claim you make must trace to something in the scan output. If you find
yourself writing "this probably uses..." — stop, and put it in *Questions I
could not answer* instead. A confident wrong answer costs a newcomer a day.
