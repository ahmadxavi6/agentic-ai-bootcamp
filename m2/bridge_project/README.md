# Module 2 Bridge Project — LangGraph vs CrewAI

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock.txt
```

Create a `.env` file in the project root:

```env
OPENROUTER_API_KEY=sk-or-...
```

## Run commands

```bash
cd m2/bridge_project
python3 bridge_project_langgraph.py "Anthropic was founded by former OpenAI employees"
python3 bridge_project_langgraph.py "the flurbotron 9000 was released in 2019"
python3 bridge_project_crewai.py "Anthropic was founded by former OpenAI employees"
python3 bridge_project_crewai.py "the flurbotron 9000 was released in 2019"
```

## Saved outputs

- LangGraph, real claim: [outputs/langgraph_real.txt](outputs/langgraph_real.txt)
- LangGraph, nonsense claim: [outputs/langgraph_nonsense.txt](outputs/langgraph_nonsense.txt)
- CrewAI, real claim: [outputs/crewai_real.txt](outputs/crewai_real.txt)
- CrewAI, nonsense claim: [outputs/crewai_nonsense.txt](outputs/crewai_nonsense.txt)

The CrewAI version here is the single-agent variant: one `Researcher-Writer`
agent runs two tasks (`research_task`, `write_task`) under
`Process.hierarchical` with a manager built on top. The manager has only one
worker to delegate to, so hierarchical adds a relay layer, not a real choice
between agents.

## 1. Which framework would you ship for your use case, and why?

LangGraph. The thing I actually need — "never answer if the evidence is
thin, and prove it" — is a Python `if` statement in LangGraph
(`choose_next`/`read_verdict`) and a hopeful instruction sentence in CrewAI.
I can unit-test `read_verdict("NOT_ENOUGH")` without touching an LLM. There
is no equivalent test for "will the CrewAI manager always honor the
backstory." CrewAI would be the pick if I mainly wanted less orchestration
code to write and could tolerate probabilistic compliance instead of
guaranteed compliance — this use case (a claim-verification desk) can't
tolerate that.

## 2. On the nonsense query — did each version refuse? Paste what they actually produced.

Both refused. Neither invented a release date for the "flurbotron 9000."

**LangGraph** (`outputs/langgraph_nonsense.txt`):

```
VERDICT : NOT_ENOUGH
ROUTE   : REPORT_GAP
======================================================================
This claim about the flurbotron 9000 could not be verified.
- There is no available information or documentation regarding the release of the flurbotron 9000.
- No credible sources or references were found that mention the product or its release date.
NEXT SEARCH: "flurbotron 9000 release date"
```

**CrewAI** (`outputs/crewai_nonsense.txt`):

```
VERDICT: COULD NOT VERIFY
It could not be verified whether the flurbotron 9000 was released in 2019,
as there is no available evidence to support this claim.
NEXT SEARCH: flurbotron 9000 release date
```

## 3. Where does the decision live in each one? Which could you prove to a customer who asks "how do I know it will never make something up?"

**LangGraph:** the decision lives in `read_verdict()` and `choose_next()`
in `bridge_project_langgraph.py` — plain Python string matching on the
model's last line, feeding a `Literal["write_answer", "report_gap"]`
router. `report_gap` is a distinct node that has no path to producing an
"answer" field; the graph's edges are the proof. I can show a customer the
source file and the two functions and they can verify the branch by
reading it, no LLM run required.

**CrewAI:** the decision lives entirely inside the manager agent's private
reasoning, expressed only as free text starting with `VERDICT: ANSWERED`
or `VERDICT: COULD NOT VERIFY` — a convention I asked for in a prompt, not
something the framework enforces. Running it also showed the boundary is
weaker than intended: the transcripts show every task — including the
"Do NOT use the Web Search tool for this task" write step — was executed
by `Agent: Crew Manager` directly, never delegated to the `Researcher-Writer`
worker agent at all. CrewAI's own `Task.tools` resolution has no way to give
one agent zero tools on one task and full tools on another (an empty list is
treated as "unset" and refilled from the agent's tools, both at task
construction and at execution time — I checked this directly against the
installed library, not from memory). So the only thing standing between the
manager and "helpfully" filling in an answer from its own training data is
whatever it decided to do with a paragraph of instructions. I could not
prove this to a customer beyond "it complied on these two test runs."

## 4. Your report_gap ended with `NEXT SEARCH: ...`. Why couldn't your agent run that search?

My graph is a single-pass DAG: `report_gap` has an edge straight to `END`,
and nothing feeds its `NEXT SEARCH` text back into `plan_query` or
`run_search`. Even if such an edge existed, there's no retry counter in
`DeskState` to bound the loop, so the graph has no mechanism to decide when
to stop retrying versus loop forever on a genuinely unanswerable claim.

