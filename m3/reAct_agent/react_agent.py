from typing import TypedDict, Literal, Optional
import os
import re
from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI

load_dotenv()
load_dotenv(find_dotenv(usecwd=True))

MAX_STEPS = 8
MAX_REPLANS = 5

TRACE = True         

def log(tag: str, msg: str = "") -> None:
    """Trace which node is running. Each line is tagged with the node name, so
    the printout reads as the actual path taken through the graph."""
    if TRACE:
        print(f"[{tag:<8}] {msg}")


# Every model call is a WAKE-UP. The model remembers NOTHING from the previous
# one - it opens its eyes, reads the prompt it was handed, answers, and forgets.
# Numbering them makes two things visible at once: how little each call knows,
# and what planning actually costs (every wake-up is a billed round-trip).
WAKE_UPS: dict[str, int] = {}


def wake_up(who: str) -> int:
    """Count one model call and print a banner marking where it happens.

    The banner is the point. Each one is a model opening its eyes knowing only
    what this prompt says - it remembers nothing from the block above. The
    [act], [is_done] and [executor] lines inside a block are YOUR code reacting
    to that decision, and they are the only reason anything crosses a banner
    at all: whatever they write into state is what the next wake-up gets to see.
    """
    WAKE_UPS[who] = WAKE_UPS.get(who, 0) + 1
    n = sum(WAKE_UPS.values())
    if TRACE:
        print("=" * 70)
        print(f"#wakeup-{n}   ({who})")
        print("=" * 70)
    return n

api_key = os.environ.get("OPENROUTER_API_KEY")
base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

llm = ChatOpenAI(
    model="openai/gpt-4o-mini", temperature=0,
    base_url=base_url,
    api_key=api_key,
    # A structured output is a few dozen tokens. Without a cap, a model that
    # starts repeating itself will happily bill you for 16k of them before
    # failing to parse. Cap it so bad generations die cheaply and fast.
    max_tokens=512,
    timeout=60,
    max_retries=2,
)


def structured(schema):
    """Bind a schema to the model.

    method="function_calling" routes through tool-calling, which is the most
    widely supported path across OpenRouter providers.
    """
    return llm.with_structured_output(schema, method="function_calling")


_ALLOWED = re.compile(r"^[0-9+\-*/().\s]+$")

def calculator(expr: str) -> str:
    """Evaluate a simple arithmetic expression.

    Never raises. A bad expression comes back as an ERROR string, which lands on
    the scratchpad like any other observation - so the model can see what it did
    wrong and try again instead of the whole graph dying mid-run.
    """
    expr = (expr or "").replace("×", "*").replace("÷", "/").replace("−", "-").strip()
    if not expr:
        return "ERROR: no expression given"
    if not _ALLOWED.match(expr):
        return "ERROR: calculator only accepts digits, + - * / ( ) . and spaces"
    try:
        return str(eval(expr, {"__builtins__": {}}, {}))
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


# The tool registry - the ONE place that says what this agent can actually DO.
# `act` dispatches through it, and Action.tool is a Literal over these names
# (plus "final_answer", which is not a tool - it is how the loop exits).
TOOLS = {
    "calculator": calculator,
}


# ---------------------------------------------------------------------------
# Schemas (structured outputs)
# ---------------------------------------------------------------------------
class Action(BaseModel):
    """Step 2: the schema-validated action the model must return.

    NOTE: every field is explicitly typed. Do NOT use `args: dict` - strict
    structured-output mode requires additionalProperties:false on every object,
    and a bare dict cannot express that (the provider returns HTTP 400).
    """
    tool: Literal["calculator", "final_answer"]
    expr: Optional[str] = Field(
        default=None, description="Arithmetic expression, when tool='calculator'.")
    text: Optional[str] = Field(
        default=None, description="The answer text, when tool='final_answer'.")


class Plan(BaseModel):
    """Step 6: an ordered list of concrete, tool-executable steps."""
    steps: list[str]


class ReplanDecision(BaseModel):
    """Step 8: replan's two options, in one flat schema.

    Two separate schemas would need a Union, and strict structured-output mode
    handles a flat object with a boolean discriminator far more reliably.
    """
    finished: bool = Field(
        description="True if past_steps already contain everything needed to answer.")
    answer: Optional[str] = Field(
        default=None, description="The final answer, when finished=True.")
    steps: list[str] = Field(
        default_factory=list,
        description="The REMAINING steps still to run, when finished=False.")


# ---------------------------------------------------------------------------
# Graph state
# ---------------------------------------------------------------------------
class State(TypedDict):
    question: str
    scratchpad: list
    action: Optional[dict]
    answer: Optional[str]
    plan: list
    past_steps: list
    steps_used: int       # Step 5: the MAX_STEPS budget counter
    replans: int          # Step 8: the MAX_REPLANS budget counter
    tool_calls: list      # audit trail: (tool_name, args, result) per invocation


# ---------------------------------------------------------------------------
# PART 1 — ReAct nodes
# ---------------------------------------------------------------------------
action_llm = structured(Action)

REACT_RULES = """\
You are an agent that WORKS OUT numeric answers instead of guessing them.

You cannot do arithmetic in your head. Every calculation goes through the
calculator tool, one call per turn.

Pick exactly ONE action:
  tool="calculator"    -> expr = one arithmetic expression, using only 0-9 + - * / ( ) .
  tool="final_answer"  -> text = the answer, stated plainly

Rules:
- Read the notepad first. If a number is already on it, reuse it - never recompute.
- Substitute known results into the next expression (e.g. notepad says 437, so
  ask for "437 + 100", not "(23 * 19) + 100" again).
- Only use final_answer once every part of the question is settled by a
  calculator result on the notepad.
"""


def _render_pad(scratchpad: list) -> str:
    """The model has NO memory between calls - the notepad IS its memory."""
    return "\n".join(scratchpad) if scratchpad else "(empty - nothing computed yet)"


def reason(state: State) -> State:
    """THINK: read the question + notepad, decide ONE next move.

    The Action schema does the parsing for us - no json.loads, no regex, no
    stripping code fences. If the model returns something off-schema the
    provider rejects it, not us.
    """
    prompt = (
        f"{REACT_RULES}\n"
        f"Question: {state['question']}\n\n"
        f"Notepad (everything known so far):\n{_render_pad(state['scratchpad'])}\n\n"
        "What is your ONE next action?"
    )
    wake_up("reason")
    log("reason", f"notepad has {len(state['scratchpad'])} line(s), "
                  f"step {state['steps_used'] + 1}")
    action: Action = action_llm.invoke(prompt)
    state["action"] = action.model_dump()
    state["steps_used"] = state.get("steps_used", 0) + 1

    chose = action.tool if action.tool in TOOLS else f"{action.tool} (not a tool - exits the loop)"
    log("reason", f"chose: {chose}")
    return state


def act(state: State) -> State:
    """DO: run what the model asked for. No AI in this function at all."""
    action = state.get("action") or {}
    tool = action.get("tool")

    if tool == "final_answer":
        state["answer"] = (action.get("text") or "").strip() or "(empty answer)"
        log("act", f"no tool needed - final_answer: {state['answer']}")
        return state

    # Dispatch through the registry, so an unknown tool is an observation the
    # model can recover from rather than a KeyError that kills the graph.
    expr = action.get("expr") or ""
    tool_fn = TOOLS.get(tool)
    if tool_fn is None:
        result = f"ERROR: unknown tool {tool!r}. Available: {', '.join(TOOLS)}"
    else:
        result = tool_fn(expr)

    # OBSERVE: if it isn't written down here, the next reason() cannot see it.
    state["scratchpad"].append(f"{tool}({expr}) = {result}")
    state["tool_calls"] = state.get("tool_calls", []) + [(tool, expr, result)]
    log("act", f"{tool}(expr={expr!r}) -> {result}")

    # WE stop the loop, not the model. Exit gracefully with the working shown.
    if state.get("steps_used", 0) >= MAX_STEPS:
        state["answer"] = (
            f"Stopped after {MAX_STEPS} steps without a final answer. "
            f"Working so far: {'; '.join(state['scratchpad'])}"
        )
        log("act", f"STEP BUDGET SPENT ({MAX_STEPS}) - stopping")
    return state


def is_done(state: State) -> str:
    """THE ROUTER. Runs no model, writes no state. It only names the next node."""
    nxt = "end" if state.get("answer") else "loop"
    log("is_done", f"-> {nxt}")
    return nxt


# ---------------------------------------------------------------------------
# PART 2 — Planning nodes
# ---------------------------------------------------------------------------
PLANNER_RULES = """\
Break the goal below into the SHORTEST ordered list of steps that solves it.

Each step must be ONE concrete action the tools can actually perform. The only
tool available is a calculator (digits and + - * / ( ) only).

Good:  "Add 12 + 19 + 8 to get the total story points"
Bad:   "Analyse the sprint data"        <- not a single action, no tool can run it
Bad:   "Add the points, then divide"    <- that is two steps, split it

Include a step for every part of the question, including any comparison.
Do not add a step for writing the final answer - that happens automatically.
"""


def planner(state: State) -> State:
    """Decide ALL the steps up front, before any of them run.

    This is the difference from Part 1: plain ReAct picks one move at a time and
    wanders on longer tasks. A plan commits to the shape of the solution first.
    """
    log("planner", f"goal: {state['question']}")
    log("planner", f"tools available: {', '.join(TOOLS)}")
    prompt = f"{PLANNER_RULES}\nGoal: {state['question']}"
    wake_up("planner")
    log("planner", "deciding every step up front")
    plan: Plan = structured(Plan).invoke(prompt)
    state["plan"] = [s for s in plan.steps if s.strip()]
    state["past_steps"] = []

    log("planner", f"plan has {len(state['plan'])} step(s):")
    for i, step in enumerate(state["plan"], 1):
        log("planner", f"    {i}. {step}")
    return state


def executor(state: State) -> State:
    """Run the NEXT plan step - and only that step - using the Part 1 ReAct loop.

    The sub-agent gets the overall goal plus what previous steps found, because
    step 2 usually needs step 1's number and the model remembers nothing.
    """
    if not state["plan"]:
        log("executor", "nothing left in the plan - skipping")
        return state

    step = state["plan"][0]
    log("executor", f"running: {step}")
    log("executor", f"({len(state['plan']) - 1} step(s) will remain) -> handing to the ReAct loop")
    done_so_far = "\n".join(f"- {s} -> {o}" for s, o in state["past_steps"]) or "(nothing yet)"

    sub_state: State = {
        "question": (
            f"Overall goal: {state['question']}\n\n"
            f"Steps already completed:\n{done_so_far}\n\n"
            f"Do ONLY this one step, then give final_answer with its result: {step}"
        ),
        "scratchpad": list(state["scratchpad"]),
        "action": None,
        "answer": None,
        "plan": [],
        "past_steps": [],
        "steps_used": 0,
        "replans": 0,
        "tool_calls": list(state.get("tool_calls", [])),
    }
    result = build_react_graph().invoke(sub_state, {"recursion_limit": 2 * MAX_STEPS + 4})

    observation = result.get("answer") or "(no result)"
    before = len(state.get("tool_calls", []))
    state["scratchpad"] = result["scratchpad"]
    state["tool_calls"] = result.get("tool_calls", [])
    state["past_steps"] = state["past_steps"] + [(step, observation)]
    state["plan"] = state["plan"][1:]

    used = [name for name, _, _ in state["tool_calls"][before:]] or ["none"]
    log("executor", f"observed: {observation}")
    log("executor", f"tools used for this step: {', '.join(used)}")
    return state


def replan(state: State) -> State:
    """Look at what ACTUALLY happened and either finish or revise the plan."""
    state["replans"] = state.get("replans", 0) + 1
    out_of_budget = state["replans"] >= MAX_REPLANS

    done_so_far = "\n".join(f"- {s} -> {o}" for s, o in state["past_steps"]) or "(nothing yet)"
    remaining = "\n".join(f"- {s}" for s in state["plan"]) or "(none left)"

    prompt = (
        f"Goal: {state['question']}\n\n"
        f"Steps completed and what they returned:\n{done_so_far}\n\n"
        f"Steps still planned:\n{remaining}\n\n"
        "If the completed steps already contain every number needed, set "
        "finished=true and write the answer, quoting the actual computed values. "
        "Otherwise set finished=false and list only the steps STILL to run "
        "(revise them if what happened makes the old plan wrong)."
    )
    if out_of_budget or not state["plan"]:
        prompt += (
            "\n\nIMPORTANT: no further steps may run. You MUST set finished=true "
            "and answer with what you already have."
        )

    wake_up("replan")
    log("replan", f"reviewing {len(state['past_steps'])} completed step(s), "
                  f"{len(state['plan'])} still planned")
    decision: ReplanDecision = structured(ReplanDecision).invoke(prompt)

    # WE decide when it stops. A model that says "not finished" with nothing left
    # to run, or that blows the budget, gets finished anyway.
    if decision.finished or out_of_budget or not decision.steps:
        state["answer"] = (decision.answer or "").strip() or (
            f"Stopped without a clean answer. Working: {done_so_far}"
        )
        why = "model says finished" if decision.finished else (
            "replan budget spent" if out_of_budget else "no steps left to run")
        log("replan", f"FINISH ({why})")
    else:
        state["plan"] = [s for s in decision.steps if s.strip()]
        log("replan", f"CONTINUE - {len(state['plan'])} step(s) still to run:")
        for i, step in enumerate(state["plan"], 1):
            log("replan", f"    {i}. {step}")
    return state


def replan_done(state: State) -> str:
    """THE ROUTER. Names the next node, nothing else."""
    return "end" if state.get("answer") else "loop"


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------
def build_react_graph():
    """Part 1 graph: reason -> act -> (loop|END)."""
    g = StateGraph(State)
    g.add_node("reason", reason)
    g.add_node("act", act)
    g.set_entry_point("reason")
    g.add_edge("reason", "act")
    # THE ARROW BACK. This is what Module 2's report_gap was missing.
    g.add_conditional_edges("act", is_done, {"end": END, "loop": "reason"})
    return g.compile()


def build_plan_execute_graph():
    """Part 2 graph: planner -> executor -> replan -> (loop|END)."""
    g = StateGraph(State)
    g.add_node("planner", planner)
    g.add_node("executor", executor)
    g.add_node("replan", replan)

    g.set_entry_point("planner")
    g.add_edge("planner", "executor")
    g.add_edge("executor", "replan")
    # Note the loop goes back to EXECUTOR, not planner: replan already produced
    # the revised remaining steps, so re-planning from scratch would undo it.
    g.add_conditional_edges("replan", replan_done, {"end": END, "loop": "executor"})
    return g.compile()


def fresh_state(question: str) -> State:
    return {
        "question": question, "scratchpad": [], "action": None, "answer": None,
        "plan": [], "past_steps": [], "steps_used": 0, "replans": 0,
        "tool_calls": [],
    }


if __name__ == "__main__":
    if not api_key:
        raise SystemExit(
            "OPENROUTER_API_KEY not found.\n"
            "Create a file named .env in the project folder containing:\n"
            "    OPENROUTER_API_KEY=sk-or-...\n"
            "then run this script again."
        )

    question = ("A team has 3 sprints of 12, 19, and 8 story points. "
                "What's the average per sprint, and is it above 12?")


    app = build_plan_execute_graph()
    WAKE_UPS.clear()

    print("=" * 70)
    print(f"QUESTION : {question}")
    print("=" * 70)
    result = app.invoke(fresh_state(question), {"recursion_limit": 3 * MAX_REPLANS + 6})

    print("=" * 70)
    print(f"ANSWER   : {result['answer']}")

    tool_calls = result.get("tool_calls", [])
    tally = {}
    for name, _, _ in tool_calls:
        tally[name] = tally.get(name, 0) + 1
    print(f"TOOLS    : {len(tool_calls)} call(s) - "
          f"{', '.join(f'{n} x{c}' for n, c in tally.items()) or 'none'}")
    for name, args, out in tool_calls:
        print(f"           {name}({args!r}) -> {out}")
    print(f"WAKE-UPS : {sum(WAKE_UPS.values())} model call(s) - "
          f"{', '.join(f'{who} x{n}' for who, n in WAKE_UPS.items())}")
    print(f"COST     : {sum(WAKE_UPS.values())} wake-up(s) to make "
          f"{len(tool_calls)} tool call(s) - that is what planning costs")
    print("=" * 70)

    # -----------------------------------------------------------------------
    # Step 9: the graphs, drawn from the compiled graph itself - not from a
    # diagram someone typed by hand, so it cannot drift from the code.
    # Paste either block into https://mermaid.live to see it.
    # -----------------------------------------------------------------------
    print()
    print("MERMAID - Part 1, the ReAct loop (this runs inside every executor step)")
    print("-" * 70)
    print(build_react_graph().get_graph().draw_mermaid())

    print("MERMAID - Part 2, plan and execute (the graph that just ran)")
    print("-" * 70)
    print(app.get_graph().draw_mermaid())

    