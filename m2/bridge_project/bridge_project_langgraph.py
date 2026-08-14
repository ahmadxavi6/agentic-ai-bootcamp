"""
Module 2 Bridge Project - LangGraph STARTER

Build an agent that searches the web, decides whether what it found is good
enough, and then does ONE OF TWO different things.

    question
       |
    plan_query    (LLM)   turn the question into a good search query
       |
    run_search    (TOOL)  a real web call - no model in this node at all
       |
    assess        (LLM)   is this evidence good enough to answer honestly?
       |
       +--- ENOUGH -----> write_answer   answer, and cite the source URLs
       |
       +--- NOT_ENOUGH -> report_gap     do NOT answer. say what is missing.

This is the first thing you have built where the path is not decided in
advance. Everything before today ran the same steps in the same order every
single time. This one asks a question and goes a different way depending on
the answer.

The search tool is already written for you in ../search_tools.py. You do not
need an API key for it and you do not need to install anything.

Run:
    python research_langgraph_starter.py "Anthropic was founded by ex-OpenAI staff"
    python research_langgraph_starter.py "the flurbotron 9000 was released in 2019"

The second one is nonsense on purpose. Your agent must refuse it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Literal, TypedDict

from dotenv import find_dotenv, load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from search_tools import NO_RESULTS, SEARCH_UNAVAILABLE, web_search  # noqa: E402

load_dotenv()
load_dotenv(find_dotenv(usecwd=True))

api_key = os.environ.get("OPENROUTER_API_KEY")
base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
if not api_key:
    raise RuntimeError(
        "OPENROUTER_API_KEY not found.\n"
        "Create a file named .env in the project folder containing:\n"
        "    OPENROUTER_API_KEY=sk-or-...\n"
        "then run this script again."
    )


llm = ChatOpenAI(
    model="openai/gpt-4o-mini",
    temperature=0,
    base_url=base_url,
    api_key=api_key,
)


# ---------------------------------------------------------------------------
# STATE - the luggage that travels the route.
# ---------------------------------------------------------------------------
class DeskState(TypedDict):
    question: str      # the claim or topic that came in
    query: str         # plan_query writes here
    evidence: str      # run_search writes here
    verdict: str       # assess writes here  <- THIS DRIVES THE ROUTE
    reasoning: str     # assess writes here
    output: str        # write_answer OR report_gap writes here
    route_taken: str   # so you can PROVE which path ran


def plan_query(state: DeskState) -> DeskState:
    """Node 1: turn the question into something worth searching for."""
    prompt = (
        "Turn the following question or claim into ONE short, effective web "
        "search query. Reply with ONLY the query text itself - no quotes, no "
        "preamble like 'Here is a good query:', no explanation.\n\n"
        f"Question: {state['question']}"
    )
    response = llm.invoke(prompt)
    state["query"] = response.content.strip().strip('"')
    return state


def run_search(state: DeskState) -> DeskState:
    """Node 2: the tool. There is no model call in this node at all."""
    state["evidence"] = web_search(state["query"])
    return state


def assess(state: DeskState) -> DeskState:
    """Node 3: is this evidence actually good enough to answer with?"""
    if state["evidence"] == SEARCH_UNAVAILABLE:
        state["verdict"] = "NOT_ENOUGH"
        state["reasoning"] = "Search was unavailable - the network or service could not be reached, so nothing was looked up."
        return state

    if state["evidence"] == NO_RESULTS:
        state["verdict"] = "NOT_ENOUGH"
        state["reasoning"] = "Search ran successfully but found nothing useful for this query."
        return state

    prompt = (
        "Question: " + state["question"] + "\n\n"
        "Evidence found:\n" + state["evidence"] + "\n\n"
        "Does this evidence provide enough information to answer the question "
        "honestly and accurately? Give 1-3 short bullet points of reasoning, "
        "then on the FINAL line write exactly one word, nothing else: "
        "ENOUGH or NOT_ENOUGH."
    )
    response = llm.invoke(prompt)
    raw = response.content.strip()
    state["reasoning"] = raw
    state["verdict"] = read_verdict(raw)
    return state


def read_verdict(raw: str) -> str:
    """Pull the verdict out of the model's free text.

    TODO 6 - return "ENOUGH" or "NOT_ENOUGH".

    Read this carefully. There are two traps in four lines.

      1. The model does not reliably obey "one word on the last line". You
         will see "FINAL: NOT_ENOUGH", a trailing full stop, a whole polite
         sentence. Take the last non-empty line and look inside it.

      2. There is a much nastier one hiding in the two words themselves.
         Look at them. Really look:

             ENOUGH
             NOT_ENOUGH

         If you get this wrong, your agent will confidently answer questions
         it has no evidence for, and NOTHING will error. No exception, no
         warning. Just a wrong answer delivered with total confidence.

    Also decide what to do when you cannot tell. There is a safe direction
    and an unsafe one. Pick the safe one.
    """
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return "NOT_ENOUGH"

    last = lines[-1].upper()
    # Check the longer/more-specific word FIRST: "ENOUGH" is a substring of
    # "NOT_ENOUGH", so testing for "ENOUGH" first would misread every
    # NOT_ENOUGH verdict as ENOUGH.
    if "NOT_ENOUGH" in last or "NOT ENOUGH" in last:
        return "NOT_ENOUGH"
    if "ENOUGH" in last:
        return "ENOUGH"

    # Can't tell -> fail safe, do not answer.
    return "NOT_ENOUGH"


def choose_next(state: DeskState) -> Literal["write_answer", "report_gap"]:
    """THE ROUTER. Runs no model, writes no state. It only names the next node."""
    return "write_answer" if state["verdict"] == "ENOUGH" else "report_gap"


def write_answer(state: DeskState) -> DeskState:
    """Node 4a: the ENOUGH path."""
    prompt = (
        "Answer the question using ONLY the evidence below. Every claim must "
        "come from the evidence - invent nothing. Quote at least one source "
        "URL from the evidence. If part of the question is not covered by the "
        "evidence, say so explicitly. Keep the whole answer under 180 words.\n\n"
        f"Question: {state['question']}\n\n"
        f"Evidence:\n{state['evidence']}"
    )
    response = llm.invoke(prompt)
    state["output"] = response.content.strip()
    state["route_taken"] = "write_answer"
    return state


def report_gap(state: DeskState) -> DeskState:
    """Node 4b: the NOT_ENOUGH path. This node must NOT answer the question."""
    prompt = (
        "You could NOT verify the question below using the available "
        "evidence. Do NOT answer the question. Produce exactly:\n"
        "1. One sentence plainly stating this could not be verified.\n"
        "2. One or two bullets on what evidence is missing.\n"
        "3. A final line in EXACTLY this form (fill in the query):\n"
        "NEXT SEARCH: <the one query you would run next>\n\n"
        f"Question: {state['question']}\n\n"
        f"Assessment notes:\n{state['reasoning']}\n\n"
        f"Evidence gathered:\n{state['evidence']}"
    )
    response = llm.invoke(prompt)
    state["output"] = response.content.strip()
    state["route_taken"] = "report_gap"
    return state


def build_graph():
    graph = StateGraph(DeskState)

    graph.add_node("plan_query", plan_query)
    graph.add_node("run_search", run_search)
    graph.add_node("assess", assess)
    graph.add_node("write_answer", write_answer)
    graph.add_node("report_gap", report_gap)

    graph.set_entry_point("plan_query")
    graph.add_edge("plan_query", "run_search")
    graph.add_edge("run_search", "assess")

    graph.add_conditional_edges(
        "assess",              # after this node runs
        choose_next,           # call this function
        {                      # and map what it returns
            "write_answer": "write_answer",
            "report_gap":   "report_gap",
        },
    )

    graph.add_edge("write_answer", END)
    graph.add_edge("report_gap", END)

    return graph.compile()


def run(question: str) -> DeskState:
    return build_graph().invoke({
        "question": question,
        "query": "",
        "evidence": "",
        "verdict": "",
        "reasoning": "",
        "output": "",
        "route_taken": "",
    })


def main() -> int:
    question = " ".join(sys.argv[1:]).strip() or \
        "Anthropic was founded by former OpenAI employees"

    result = run(question)

    print("=" * 70)
    print(f"QUESTION : {result['question']}")
    print("=" * 70)
    print(f"\n[1] SEARCH QUERY\n{result['query']}")
    print(f"\n[2] EVIDENCE ({len(result['evidence'])} chars)")
    print(result["evidence"][:700])
    print(f"\n[3] ASSESSMENT\n{result['reasoning']}")
    print("\n" + "=" * 70)
    print(f"VERDICT : {result['verdict']}")
    print(f"ROUTE   : {result['route_taken'].upper()}")
    print("=" * 70)
    print(result["output"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())