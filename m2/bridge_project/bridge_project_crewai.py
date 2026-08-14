"""
Module 2 Bridge Project - CrewAI STARTER (single agent, hierarchical)

Same job as the LangGraph version. Build that one FIRST, then come back here.

WHAT IS DIFFERENT
    ONE agent does both the research and the writing, as two Tasks. A
    manager is still built on top (Process.hierarchical, manager_llm=llm)
    and relays the work to it - but with only one worker agent, the manager
    has no one else to delegate to, so it isn't really choosing anything.

    The agent keeps the Web Search tool for both tasks. CrewAI has no
    supported way to strip a tool from one task and not another for the
    same agent (an empty tools=[] on a Task is silently treated as "not
    specified" and refilled from the agent's own tools - checked against
    the installed version, not assumed). So "don't search while writing" is
    enforced the same way "refuse when the evidence is thin" is enforced
    everywhere else in this file: as an instruction, not a code path.

    Run both versions on the nonsense claim afterwards and watch carefully.
    In LangGraph, refusing is a code path - report_gap physically cannot
    produce an answer. Here, both the refusal AND the tool boundary are
    requests written into a prompt. Whether the agent still listens to
    either one is the interesting result, and it goes in your README
    either way.

Run:
    python research_crewai_starter.py "Anthropic was founded by ex-OpenAI staff"
    python research_crewai_starter.py "the flurbotron 9000 was released in 2019"
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# CrewAI asks about execution traces on the first run in a new folder and
# blocks for 20 seconds waiting for an answer. This stops that.
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")

from crewai import Agent, Crew, LLM, Process, Task  # noqa: E402
from crewai.tools import tool  # noqa: E402
from dotenv import find_dotenv, load_dotenv  # noqa: E402

try:
    from crewai.events.listeners.tracing.utils import mark_first_execution_done

    mark_first_execution_done()
except Exception:      # different CrewAI version - the prompt times out anyway
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from search_tools import web_search  # noqa: E402

load_dotenv()
load_dotenv(find_dotenv(usecwd=True))

api_key = os.environ.get("OPENROUTER_API_KEY")
if not api_key:
    raise RuntimeError(
        "OPENROUTER_API_KEY not found.\n"
        "Create a file named .env in the project folder containing:\n"
        "    OPENROUTER_API_KEY=sk-or-...\n"
        "then run this script again."
    )


llm = LLM(
    model="openrouter/openai/gpt-4o-mini",
    temperature=0,
    api_key=api_key,
)


# ---------------------------------------------------------------------------
# THE TOOL
# ---------------------------------------------------------------------------
# In LangGraph the tool was a plain function call inside a node - YOU decided
# when it ran. Here you hand the tool to an agent and the agent decides.
#
# TODO 2 - finish the docstring below.
#
#          The docstring is NOT a comment. It is the description the model
#          reads when deciding whether to use this tool, and what to pass it.
#          Write it for the model, not for yourself.
#
#          It should say what the tool searches, that it returns findings with
#          source URLs, and that it can return the exact text NO_RESULTS or
#          SEARCH_UNAVAILABLE.
@tool("Web Search")
def search_web(query: str) -> str:
    """Search the web for evidence about a claim or question.

    Pass ONE short, focused search query. Returns a plain-text block of
    numbered findings, each with a source URL that must be preserved and
    reported alongside any claim drawn from it.

    Two exact strings can come back instead of findings:
        NO_RESULTS          the search ran but found nothing useful
        SEARCH_UNAVAILABLE  the network or the search service could not be reached
    These are different situations and must be reported as such, not treated
    as the same kind of failure.
    """
    return web_search(query)


def build_crew() -> Crew:
    # ONE agent, two roles. It keeps the Web Search tool for both tasks -
    # CrewAI has no supported way to give a single agent zero tools on one
    # task and full tools on another (Task.tools=[] gets silently refilled
    # from the agent's own tools, both at construction and at execution
    # time). So the writing-phase boundary below is enforced the same way
    # refusal is enforced in the rest of this file: as an instruction the
    # agent is asked to follow, not a physical restriction.
    agent = Agent(
        role="Researcher-Writer",
        goal=(
            "Find real evidence for the given question, then turn it into an "
            "honest final answer, or an honest refusal"
        ),
        backstory=(
            "You work in two strict phases. In the RESEARCH phase you use the "
            "Web Search tool and report exactly what it returned, keeping every "
            "source URL attached to the claim it supports. You never fill gaps "
            "from your own memory. NO_RESULTS ('search ran, found nothing') and "
            "SEARCH_UNAVAILABLE ('search could not run at all') are different "
            "outcomes and you never blur them together.\n\n"
            "In the WRITING phase you do NOT have the search tool anymore - you "
            "write using ONLY the findings already gathered in the research "
            "phase. You never add facts from your own knowledge, no matter how "
            "confident you feel about them. You would much rather hand back "
            "'we could not verify this' than something polished that might be "
            "wrong."
        ),
        tools=[search_web],
        llm=llm,
        verbose=True,
        max_iter=4,
    )

    # -----------------------------------------------------------------------
    # THE TASKS
    # -----------------------------------------------------------------------
    # agent= is set explicitly on both tasks, which under a hierarchical
    # process pins the manager's delegation to this one worker for each
    # task (see Crew._update_manager_tools) rather than leaving it to pick
    # from a pool.

    # TODO 5 - the research task.
    #          Use {question}, which is filled in by kickoff(inputs=...).
    #          Tell it to use the Web Search tool, report exactly what came
    #          back including source URLs, and NOT to substitute its own
    #          knowledge if the search returned nothing.
    research_task = Task(
        description=(
            "Find evidence about the following question or claim, using the "
            "Web Search tool:\n\n{question}\n\n"
            "Report exactly what the search returned, including every source "
            "URL. Do NOT substitute your own knowledge if the search returns "
            "NO_RESULTS or SEARCH_UNAVAILABLE - report that outcome plainly "
            "instead."
        ),
        expected_output=(
            "A list of findings with source URLs, OR a plain statement that "
            "the search found nothing (NO_RESULTS) or could not run "
            "(SEARCH_UNAVAILABLE)."
        ),
        agent=agent,
    )

    # TODO 6 - the writing task. This is where the branch lives now.
    #          It must produce ONE of two things:
    #
    #            - if the evidence supports an answer: under 180 words,
    #              quoting at least one source URL
    #            - if it does NOT: no answer at all. One sentence saying it
    #              could not be verified, what is missing, and a final line
    #              in exactly this form:
    #                  NEXT SEARCH: <the one query you would run next>
    #
    #          Ask it to begin with either "VERDICT: ANSWERED" or
    #          "VERDICT: COULD NOT VERIFY" so you can log what happened.
    write_task = Task(
        description=(
            "Do NOT use the Web Search tool for this task, even though you "
            "have it available. Using ONLY the findings already produced by "
            "the research task above, produce the final output for:\n\n"
            "{question}\n\n"
            "Begin your response with exactly one of these two lines:\n"
            "VERDICT: ANSWERED\n"
            "VERDICT: COULD NOT VERIFY\n\n"
            "If the evidence supports an answer: write VERDICT: ANSWERED, then "
            "under 180 words answering the question, quoting at least one "
            "source URL from the findings.\n\n"
            "If the evidence does NOT support an answer: write "
            "VERDICT: COULD NOT VERIFY, then do not answer the question at "
            "all. Write one sentence saying it could not be verified, state "
            "what evidence is missing, and end with a final line in exactly "
            "this form:\n"
            "NEXT SEARCH: <the one query you would run next>"
        ),
        expected_output=(
            "Either a VERDICT: ANSWERED block with a sourced answer under 180 "
            "words, or a VERDICT: COULD NOT VERIFY block ending with a "
            "NEXT SEARCH: line. Never both, never neither. No Web Search "
            "tool calls in this step."
        ),
        agent=agent,
        context=[research_task],
    )

    # Hierarchical: a manager is built on top and assigns both tasks. With
    # only one worker agent it has no one else to delegate to, so both tasks
    # land on the same agent either way - the only thing "hierarchical" adds
    # here is the manager relaying the work, not a choice between workers.
    return Crew(
        agents=[agent],
        tasks=[research_task, write_task],
        process=Process.hierarchical,
        manager_llm=llm,
        verbose=True,
        tracing=False,
    )


def main() -> int:
    question = " ".join(sys.argv[1:]).strip() or \
        "Anthropic was founded by former OpenAI employees"

    result = str(build_crew().kickoff(inputs={"question": question}))

    print("\n" + "=" * 70)
    print(f"QUESTION : {question}")
    print("=" * 70)
    print(result)

    # TODO 8 - log which way the crew went.
    #
    #          In LangGraph you read state["route_taken"], written by whichever
    #          node actually ran. There is no such field here. The only way to
    #          know what this crew decided is to read its final text and guess.
    #
    #          Write that guess below - and put one sentence about it in your
    #          README, because it is the whole difference between the two.
    if "VERDICT: ANSWERED" in result.upper():
        route = "ANSWERED"
    elif "VERDICT: COULD NOT VERIFY" in result.upper():
        route = "COULD_NOT_VERIFY"
    else:
        route = "UNKNOWN (no VERDICT line found in output)"

    print("\n" + "=" * 70)
    print(f"ROUTE : {route}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())