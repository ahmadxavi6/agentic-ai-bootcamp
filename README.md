# Agentic AI Bootcamp

A hands-on learning repository for building agentic AI systems in Python: raw agent
loops, framework-based orchestration (LangGraph and CrewAI), planning agents, and
Agent Skills. Every module ends with something runnable and a written comparison of
what the framework made explicit versus what it hid.

The recurring theme across the modules: **a rule in a prompt is advisory, a gate in
code is enforced.** Most of the write-ups exist to show where a given design put its
decisions — in Python you can unit-test, or in model text you can only hope for.

## What each module teaches

| Module | Folder | Idea |
|---|---|---|
| 1 | [m1/](m1/) | The agent loop, hand-written — no framework |
| 2 | [m2/](m2/) | LangGraph vs CrewAI on the same task, head to head |
| 3 | [m3/](m3/) | ReAct, plan-and-execute, sub-agents, and a lookup budget |
| 5B | [Module-05B-Agent-Skills/](Module-05B-Agent-Skills/) | Agent Skills and progressive disclosure |

## Project structure

```text
agentic-ai-bootcamp/
├── README.md
├── requirements.lock.txt
├── m1/
│   └── agent_loop.py                     hand-written reason → act → observe loop
├── m2/
│   ├── hello-agents/                     minimal "hello agent" in both frameworks
│   │   ├── hello_crewai.py
│   │   └── hello_langgraph.py
│   ├── error_helper/                     explain/triage a Python traceback
│   │   ├── error_helper_crewai.py
│   │   └── error_helper_langgraph.py
│   ├── study_guide/                      3-task pipeline: explain → example → quiz
│   │   ├── study_guide_langgraph.py
│   │   ├── study_guide_crewai.py
│   │   ├── study_guide_*_output.md
│   │   └── README.md
│   └── bridge_project/                   claim-verification desk, both frameworks
│       ├── bridge_project_langgraph.py
│       ├── bridge_project_crewai.py
│       ├── search_tools.py               pre-written web_search() tool
│       ├── outputs/                      saved transcripts, real + nonsense claims
│       └── README.md
├── m3/
│   ├── reAct_agent/
│   │   └── react_agent.py                ReAct loop + plan-and-execute graph
│   └── bridge-project/                   the Vendor Onboarding Desk
│       ├── vendor_desk.py                triage → screen → decide → memo
│       ├── registry_tools.py             GLEIF LEI register + OFAC sanctions list
│       ├── search_tools.py
│       ├── verify_tools.py               10 live checks against real registries
│       ├── REQUEST.md                    the incoming brief from Finance
│       └── MEMO.md                       the decision memo it produced
└── Module-05B-Agent-Skills/
    ├── SUBMISSION.md                     write-up for the sql-explainer skill
    └── skill-runner/
        ├── skill_runner.py               ~300-line skill loader, no framework
        ├── skills/                       jhf-brief, lab-grader, repo-onboarder,
        │                                 sql-explainer
        └── output/                       generated artifacts
```

Local-only paths (`.venv/`, `.env`, `.idea/`, `.claude/`, caches) are gitignored.

## Requirements

- Python 3.11+
- An OpenRouter API key
- Internet access — the m3 tools call the live GLEIF and OFAC endpoints, and
  `search_tools.py` calls Wikimedia

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock.txt
```

There is no `requirements.txt` in this repo — `requirements.lock.txt` is the pinned
set the modules were actually run against (LangGraph 1.2.10, CrewAI 1.15.14,
langchain-openai 1.4.3, openai 2.53.0).

## Environment variables

Create a `.env` file in the project root:

```env
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

The scripts load it with `python-dotenv`, so running them from either the repo root
or the module folder works. `skill_runner.py` also honours `SKILL_MODEL` if you want
to override its default model.

## Module 1 — the loop, by hand

[m1/agent_loop.py](m1/agent_loop.py) implements the agent pattern with nothing but the
`openai` SDK pointed at OpenRouter: send the prompt, parse the model's chosen action,
run a tool (`calculator`, `lookup`), append the observation, repeat until the model
emits a final answer. The model decides each step — the steps are not hardcoded.

`MAX_STEPS = 6` and `MAX_LLM_CALLS = 8` are the point of the exercise: never trust the
model to stop itself.

```bash
python m1/agent_loop.py
```

## Module 2 — LangGraph vs CrewAI

Same task, twice, so the difference between the frameworks is the only variable.

```bash
python m2/hello-agents/hello_langgraph.py
python m2/error_helper/error_helper_crewai.py

cd m2/study_guide
python3 study_guide_langgraph.py "temperature in language models"
python3 study_guide_crewai.py "temperature in language models"
```

### Bridge project — the claim-verification desk

Given a claim, search for evidence, then either answer it or refuse and say what it
would take to settle the question.

```bash
cd m2/bridge_project
python3 bridge_project_langgraph.py "Anthropic was founded by former OpenAI employees"
python3 bridge_project_langgraph.py "the flurbotron 9000 was released in 2019"
python3 bridge_project_crewai.py "Anthropic was founded by former OpenAI employees"
python3 bridge_project_crewai.py "the flurbotron 9000 was released in 2019"
```

Both versions refused the nonsense claim. The interesting part is *where the refusal
lives*: in LangGraph it is `read_verdict()` and `choose_next()` — plain Python feeding
a typed router, with `report_gap` as a node that has no path to producing an answer.
In CrewAI it is a convention requested in a prompt. Saved transcripts and the full
write-up, including why the agent couldn't run its own `NEXT SEARCH`, are in
[m2/bridge_project/README.md](m2/bridge_project/README.md).

## Module 3 — planning, sub-agents, and a budget

[m3/reAct_agent/react_agent.py](m3/reAct_agent/react_agent.py) builds two graphs and
runs the second one: a ReAct loop (`reason → act → is_done`) and a plan-and-execute
graph (`planner → executor → replan`) where the ReAct loop runs inside each executor
step. Every model call is printed as a numbered "wake-up" banner, because the model
remembers nothing between calls — whatever your code writes into state is the only
thing that crosses the boundary. The run ends with a cost tally and Mermaid diagrams
drawn from the compiled graphs, so the diagrams cannot drift from the code.

```bash
python m3/reAct_agent/react_agent.py
```

### Bridge project — the Vendor Onboarding Desk

Seven new suppliers, €2.1m a year, and a Thursday payment run
([REQUEST.md](m3/bridge-project/REQUEST.md)). The constraint is the lesson:
`MAX_LOOKUPS = 9` for seven suppliers, so the agent cannot check everything and
something has to decide what is worth checking.

```bash
cd m3/bridge-project
python verify_tools.py          # must pass before you trust anything above it
python vendor_desk.py --check   # setup check only
python vendor_desk.py           # the full run
```

`registry_tools.py` hits the real GLEIF LEI register and the real OFAC SDN list.
The three markers it returns are deliberately distinct — `NO_RECORDS` (the registry
answered and has nothing), `LOOKUP_UNAVAILABLE` (the call never completed), and
`NO_SANCTIONS_MATCH` — because "I found nothing" and "I could not look" must not
collapse into the same decision. Notably, `NO_RECORDS` does not mean a company is
fake.

The output is a decision per supplier with the evidence attached and a lookup ledger:
see [MEMO.md](m3/bridge-project/MEMO.md), where one supplier is rejected on a
sanctions match, one on a total absence of evidence, three come back with conditions,
and the rest are approved.

## Module 5B — Agent Skills

[skill_runner.py](Module-05B-Agent-Skills/skill-runner/skill_runner.py) is a skill
loader with the lid off — roughly 300 lines, no framework — that prints its token
receipts every run. Four steps: discover every `skills/*/SKILL.md` keeping only name
and description, show the model that tiny menu, load the one matching body in full,
then execute it with tools it can call (`read_resource`, `run_script`, `save_output`,
`run_subagent`).

```bash
cd Module-05B-Agent-Skills/skill-runner
python skill_runner.py --list
python skill_runner.py "Give me a one-page brief on agentic RAG for a CTO audience"
python skill_runner.py "What is 12 x 9?"     # should route to NO_SKILL
```

Step 3 is the whole trick. At 100 skills the menu is ~8,000 tokens and you load one
body of ~400, instead of ~40,000 tokens of mostly irrelevant instructions before the
user has said anything. A skill that fires on everything is a system prompt with extra
steps, so both directions are tested — firing *and* staying dormant.

Four skills live in [skills/](Module-05B-Agent-Skills/skill-runner/skills/):

- `jhf-brief` — a one-page decision brief, with `format_brief.py` enforcing word
  count, required headings, order, and a banned-phrase list
- `lab-grader` — an orchestrator: five sub-agents, one per rubric criterion, each with
  a fresh context window, so criterion 4 cannot be anchored by a mark it never saw
- `repo-onboarder` — scans a repository and explains it
- `sql-explainer` — the submitted scenario; see below

[SUBMISSION.md](Module-05B-Agent-Skills/SUBMISSION.md) is the write-up for
`sql-explainer`: paste in an inherited query, get a plain-English explanation and
concrete improvements that say *why* each one helps. The division of labour is the
design — `scan_sql.py` locates 12 anti-patterns with line numbers (regex and `len()`,
not reasoning), `optimisation-checklist.md` supplies the cost mechanism, the model
judges what matters for this query, and `check_report.py` **rejects** any finding
whose "why it costs" cell is too short or leans on a stock phrase like "best
practice". That last script is what turns the scenario's "done when" from a hope into
a gate.

## Notes

- Keep `.env`, virtual environments, and local caches out of version control.
- This is a learning repository, not production code. `m1/agent_loop.py` is derived
  from a lab starter.
- Model choice matters more than expected: in Module 5B, `gpt-4.1-nano` routed
  correctly but skipped tool steps, while `gpt-4o-mini` followed all seven. The
  recorded transcripts are `gpt-4o-mini`.

## License

Educational use. Add a license if you plan to share this beyond a learning project.

## Possible next steps

- Feed `report_gap`'s `NEXT SEARCH` back into the m2 graph, with a bounded retry
  counter in state
- Persist the m3 lookup ledger across runs so a supplier is not re-screened
- Turn the stronger experiments into reusable agent templates
