# M5B Submission — sample (deliberately imperfect)

**Student:** Sample Student

## My skill

I built a skill called `helper`. Here is my SKILL.md:

```markdown
---
name: helper
description: A skill that helps with documents.
---

# Helper

This skill helps you with documents. It can summarise them, rewrite them,
translate them, extract tables from them, and reformat them.

## Steps
1. Read the document.
2. Do what the user asked.
3. Give them the result.
```

## How I loaded it

I pasted the whole SKILL.md into my system prompt at startup, along with my two
other skills, so the agent always knows about all of them.

## Transcript

> **Me:** Summarise this contract.
> **Agent:** Here is a summary of the contract: ...

It worked well.

## Note

I made it a skill because skills are reusable. The scope is documents.
