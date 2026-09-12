"""
The Vendor Onboarding Desk - Module 3 bridge project

Read INSTRUCTIONS.md first, then REQUEST.md.

Before you touch this file:
    python verify_tools.py        <- must print "all 10 checks passed"

Everything here is scaffolding you have seen before. What is new is the
BUDGET: you cannot afford to check everything, so something has to decide
what is worth checking. That decision is the project.

    triage  ->  screen  ->  decide  ->  (loop | memo)
                  |
                  +-- hands ONE supplier to a compiled ReAct sub-agent

Run:
    python vendor_desk.py            # setup check, then the full run
    python vendor_desk.py --check    # setup check only
"""

from __future__ import annotations

import os
import sys
from typing import Literal, Optional, TypedDict

# the tools live one level up, in bridge-project/ - this lets you run the file
# from either folder without thinking about it
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from registry_tools import (
    LOOKUP_UNAVAILABLE,
    NO_RECORDS,
    NO_SANCTIONS_MATCH,
    gleif_lookup,
    sanctions_screen,
)
from search_tools import web_search

load_dotenv()

HERE = os.path.dirname(os.path.abspath(__file__))

# ===========================================================================
# THE CONSTRAINT
# ===========================================================================
# This rations the EXPENSIVE work: establishing which legal entity a supplier
# actually is. Sanctions screening is a mandatory baseline control - run it for
# everyone, always; it does not come out of this budget.
# Do not raise this number. Working inside it IS the project.
MAX_LOOKUPS = 9

BUDGET = {"used": 0}

# Every lookup that is actually spent gets a line here, so the count in the
# memo is evidence rather than an assertion.
LEDGER: list[str] = []

# No supplier may burn more than this, however interesting it looks. Without a
# per-supplier ceiling the first ambiguous name eats the whole budget and the
# suppliers at the back of the queue get nothing - which is exactly the
# failure ReAct-without-a-plan produces.
MAX_LOOKUPS_PER_SUPPLIER = 2

# ---------------------------------------------------------------------------
# THE SANCTIONS THRESHOLD - a judgement, made once, in code, where it can be
# audited. Measured against this actual list:
#
#   1.00  AL WASEL AND BABEL GENERAL TRADING LLC   [IRAQ2]   <- a real match
#   0.81  HARA COMPANY [SDGT/NPWMD/IRGC/IFSR]  vs "Almarai Company"
#   0.78  ARAB CHINA TRADING COMPANY [SDGT]    vs "Al Noor Cart Trading Company"
#   0.77  ONX TRADING FZE [SDGT]               vs "Zorblax Trading FZE"
#   0.71  MAVERIKS [RUSSIA-EO14024]            vs "Maersk A/S"
#
# Everything from 0.71 to 0.81 is noise from shared words - "Company",
# "Trading", "LLC". A threshold of 0.80 would refuse Almarai, a legitimate
# Saudi dairy business, on the strength of a shared word. 0.90 sits in the
# empty band between the loudest noise (0.81) and the one true hit (1.00).
#
# Being wrong low: we refuse honest suppliers and Rana stops trusting the
# screen. Being wrong high: we wire money to a sanctioned entity, which is a
# criminal offence. The asymmetry is why anything at or above 0.90 is treated
# as decisive and anything between 0.80 and 0.90 is reported to Rana as a
# near-miss to be cleared by a human rather than silently dropped.
SANCTIONS_DECISIVE = 0.90
SANCTIONS_NOTABLE = 0.80

TRACE = True


def log(tag: str, msg: str = "") -> None:
    if TRACE:
        print(f"[{tag:<9}] {msg}")


def spend(what: str) -> bool:
    """Call before every lookup. Returns False when the budget is gone."""
    if BUDGET["used"] >= MAX_LOOKUPS:
        return False
    BUDGET["used"] += 1
    print(f"  [{BUDGET['used']:2}/{MAX_LOOKUPS}] {what}")
    return True


# ---------------------------------------------------------------------------
# The model, and one wrapper around every call to it.
# ---------------------------------------------------------------------------
api_key = os.environ.get("OPENROUTER_API_KEY")
base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

llm = ChatOpenAI(
    model="openai/gpt-4o-mini",
    temperature=0,
    base_url=base_url,
    api_key=api_key,
    # A structured answer is a few hundred tokens. Uncapped, a model that
    # starts repeating itself bills you for 16k of them before failing to
    # parse. Capped, a bad generation dies cheaply.
    max_tokens=900,
    timeout=60,
    max_retries=2,
)


def ask(bound, prompt: str, fallback, what: str):
    """One model call, retried once, never fatal.

    The provider occasionally raises LengthFinishReasonError because the model
    failed to close a valid structured object. That is not our logic, and a run
    that has already spent real lookups must not die because of it: retry once,
    then carry on with a fallback and report the gap honestly.
    """
    for attempt in (1, 2):
        try:
            return bound.invoke(prompt)
        except Exception as e:                             # noqa: BLE001
            log("model", f"{what} failed on attempt {attempt}: {type(e).__name__}")
    log("model", f"{what} gave up after 2 attempts - using fallback")
    return fallback


# ===========================================================================
# 1 - THE SCHEMAS
# ===========================================================================
# Three decisions, three schemas - same shape as the Module 3 solution.
# Explicit fields only. `args: dict` will earn you an HTTP 400.

class Supplier(BaseModel):
    """One line out of Rana's email."""
    name: str
    jurisdiction: str = Field(
        description="Country as Procurement wrote it, e.g. 'Denmark', 'UAE'.")
    sector: str = Field(description="What they supply, e.g. 'logistics'.")
    # Of the three things Rana mentioned, only TWO can drive the plan:
    #
    #   jurisdiction    - kept. An LEI is mainly required of entities trading in
    #                     regulated financial markets, and how likely a supplier
    #                     is to have one varies by where it is incorporated, so
    #                     this changes what "not in the register" means.
    #   hand-typed names - kept, as `name_risk` below. It is not a per-supplier
    #                     fact Rana gave us, it is a property of every name on
    #                     the list, and it is the reason a near-match is expected
    #                     rather than surprising.
    #   annual value    - DELIBERATELY ABSENT. Rana gave one total (EUR 2.1m)
    #                     across seven suppliers and no split. A per-supplier
    #                     value field could only be filled by the model guessing,
    #                     and a guessed number that then decides who goes
    #                     unchecked is the worst kind of invented fact. If
    #                     Procurement sends the split, add it and rank on it.
    name_risk: str = Field(
        description="Why this exact string may not pin down one legal entity: "
                    "generic words ('Trading', 'Company'), a group name with "
                    "many similarly-named subsidiaries, transliteration, or a "
                    "likely typo. One short clause.")


class Plan(BaseModel):
    """What to check, in what order, given a budget that will run out."""
    # A bare list of names is the input. What makes this a plan is that it
    # commits to an ORDER before any lookup is spent - so when the budget runs
    # out, the suppliers left unverified are the ones we CHOSE to leave
    # unverified, and the reasoning for that choice is on the record.
    #
    # There is deliberately no `allowances: list[int]` field. The first version
    # had one, and the model spent it badly in a way that was easy to detect
    # and impossible to prompt away: it gave the supplier already settled by a
    # 1.00 sanctions match a lookup it did not need, gave Maersk and Siemens
    # zero, and left 3 of 9 lookups unspent while two suppliers went
    # unverified. Ranking is judgement and belongs to the model; dividing a
    # hard integer ceiling is arithmetic and belongs in code. See allocation
    # in screen().
    order: list[Supplier] = Field(
        description="Every supplier, re-ordered: the one whose lookup is most "
                    "likely to CHANGE the verdict goes first.")
    reasoning: str = Field(
        description="Why this order. Two or three sentences, naming which "
                    "suppliers you are willing to leave unverified and why.")


class Verdict(BaseModel):
    """The decision Rana acts on."""
    supplier: str
    verdict: Literal["APPROVE", "CONDITIONS", "REJECT", "INSUFFICIENT"]
    reason: str = Field(description="Why. In language Rana can repeat to Procurement.")
    # One field carries the whole load of making a verdict actionable, because
    # for three of the four it is the same question - what happens next?
    #   CONDITIONS   -> the specific document or identifier required, and who
    #                   from ("ask Procurement for the LEI on the invoice")
    #   REJECT       -> what Rana does instead of paying
    #   INSUFFICIENT -> the one check or document that would settle it
    #   APPROVE      -> "release the payment"
    next_step: str = Field(
        description="What Rana does next, naming the specific document, "
                    "identifier or person. Never 'investigate further'.")
    evidence: str = Field(
        description="The retrieved facts this rests on - LEI codes, statuses, "
                    "similarity scores. Only things actually returned by a "
                    "tool. If a fact is not in the evidence above, leave it out.")


class Screening(BaseModel):
    """What the sub-agent decided to look up, and what came back."""
    tool: Literal["gleif_lookup", "web_search", "final_answer"]
    name: Optional[str] = Field(
        default=None, description="Company name to look up, when tool='gleif_lookup'.")
    query: Optional[str] = Field(
        default=None, description="Search query, when tool='web_search'.")
    text: Optional[str] = Field(
        default=None, description="Factual summary of what was established, "
                                 "when tool='final_answer'.")


PLAN_LLM = llm.with_structured_output(Plan, method="function_calling")
VERDICT_LLM = llm.with_structured_output(Verdict, method="function_calling")
SCREEN_LLM = llm.with_structured_output(Screening, method="function_calling")


# ===========================================================================
# 2 - THE STATE
# ===========================================================================

class State(TypedDict):
    request: str              # the raw email
    queue: list               # suppliers not yet screened
    evidence: list            # what the registries actually returned
    verdicts: list            # one per supplier
    skipped: list             # named, never hidden
    plan_reasoning: str       # why this order - goes in the memo, not the log
    screened: list            # the evidence bundle for the supplier just done


# ---------------------------------------------------------------------------
# helpers used by more than one node
# ---------------------------------------------------------------------------
def top_sanctions_score(report: str) -> float:
    """Highest similarity in a sanctions report. 0.0 if there is nothing."""
    if report in (NO_SANCTIONS_MATCH, LOOKUP_UNAVAILABLE):
        return 0.0
    scores = []
    for line in report.splitlines():
        head = line.strip().split(" ", 1)[0]
        try:
            scores.append(float(head))
        except ValueError:
            continue
    return max(scores) if scores else 0.0


def sanctions_line(report: str) -> str:
    """The single worst entry, for quoting in a prompt or a memo."""
    if report in (NO_SANCTIONS_MATCH, LOOKUP_UNAVAILABLE):
        return report
    best, best_score = "", -1.0
    for line in report.splitlines():
        stripped = line.strip()
        head = stripped.split(" ", 1)[0]
        try:
            score = float(head)
        except ValueError:
            continue
        if score > best_score:
            best, best_score = stripped, score
    return best or report


# ===========================================================================
# 3 - YOUR NODES
# ===========================================================================

TRIAGE_RULES = """\
You are triaging a supplier list for a payment run. Extract every supplier
exactly as Procurement typed it - do not correct spelling, that is evidence.

Then decide the ORDER in which they get checked. There are only {budget}
register lookups for the whole list, so the order decides who gets verified
and who does not.

Rank FIRST the suppliers where a lookup is most likely to CHANGE the decision.
Rank LAST the ones where a lookup would only confirm what is already known.

Read these carefully, they are the traps:

- FAME IS NOT EVIDENCE. A household name is not safer, it is MORE ambiguous:
  large groups have many similarly-named legal entities, and the register
  cannot tell you which one Procurement means. Never rank a supplier last
  because you recognise the brand.
- Generic words - "Trading", "General Trading", "Company", "Works" - make a
  name hard to pin to one entity and make sanctions screening noisy.
- Procurement typed every one of these by hand from paper forms, so expect
  near-matches rather than exact ones.
- A high sanctions similarity score is NOT a verdict. The screen below is
  already done and costs nothing; treat a score as a reason to look harder,
  not as a finding.
- Do NOT assign lookup counts. You are not being asked how many lookups each
  supplier gets - that is worked out in code from your order, and a supplier
  already settled by a decisive sanctions match is given none automatically.
  Just rank them.
"""


def triage(state: State) -> State:
    """
    Read the email. Pull out the suppliers. Decide the order.

    Extracting seven names is the easy half. The half that counts is deciding
    which ones get the budget - because it will run out before the list does.

    The check we would never skip, whatever the supplier, is the sanctions
    screen: it is a legal obligation rather than a judgement call, it is free,
    and paying a listed entity is a crime. So it runs here, for ALL seven,
    before a single rationed lookup is spent - which means even a supplier we
    later have to skip for budget has been screened, and the plan gets to see
    every score before it decides where the expensive work goes.
    """
    # -- first model call: read the email, no judgement yet ------------------
    extracted = ask(
        PLAN_LLM,
        "Extract the suppliers from this email, keeping the order they appear "
        "in. Do not rank them yet.\n\n"
        f"{state['request']}",
        fallback=None,
        what="triage/extract",
    )
    if extracted is None or not extracted.order:
        log("triage", "extraction failed - nothing to screen")
        state.update(queue=[], evidence=[], verdicts=[], skipped=[],
                     plan_reasoning="Supplier extraction failed; no plan was made.",
                     screened=[])
        return state

    suppliers = extracted.order
    log("triage", f"{len(suppliers)} supplier(s) read off the email")

    # -- the mandatory baseline: screen everyone, off-budget -----------------
    log("triage", "sanctions screening all suppliers (free, mandatory, off-budget)")
    screens: dict[str, str] = {}
    for s in suppliers:
        report = sanctions_screen(s.name)
        screens[s.name] = report
        log("triage", f"  {top_sanctions_score(report):.2f}  {s.name}")

    # -- second model call: now rank, with the scores in hand ---------------
    roster = "\n".join(
        f"- {s.name} ({s.sector}, {s.jurisdiction})\n"
        f"    name risk: {s.name_risk}\n"
        f"    sanctions top hit: {sanctions_line(screens[s.name])}"
        for s in suppliers
    )
    prompt = (
        TRIAGE_RULES.format(budget=MAX_LOOKUPS)
        + f"\nA similarity of {SANCTIONS_DECISIVE:.2f} or above is treated as "
          f"decisive; below that it is noise from shared words.\n\n"
        + f"The suppliers, already screened:\n{roster}\n\n"
        + "Return every supplier in your chosen order."
    )
    plan = ask(PLAN_LLM, prompt, fallback=None, what="triage/plan")

    if plan is None or len(plan.order) != len(suppliers):
        # Ordering failed, but the screens did not. Fall back to the order
        # Procurement sent and say so, rather than dropping suppliers.
        log("triage", "ranking failed - falling back to the order as sent")
        ordered = suppliers
        reasoning = ("Ranking model call failed; suppliers were checked in the "
                     "order Procurement sent them. Sanctions screening still "
                     "ran for all of them.")
    else:
        ordered = plan.order
        reasoning = plan.reasoning

    queue = []
    for s in ordered:
        # `screens` is keyed on the name as extracted; the ranking call could
        # have tidied it, so fall back to screening on the spot rather than
        # letting a supplier through unscreened.
        report = screens.get(s.name) or sanctions_screen(s.name)
        score = top_sanctions_score(report)
        queue.append({
            "name": s.name,
            "jurisdiction": s.jurisdiction,
            "sector": s.sector,
            "name_risk": s.name_risk,
            "sanctions": report,
            "sanctions_score": score,
            # A decisive sanctions match settles the verdict on its own, and
            # the screen that produced it was free. Spending a rationed lookup
            # to learn whether a prohibited counterparty also has an LEI is
            # money taken from a supplier that is still undecided. This is a
            # threshold comparison, so it is made here, in code, once.
            "settled": score >= SANCTIONS_DECISIVE,
        })

    undecided = sum(1 for q in queue if not q["settled"])
    log("triage", f"{undecided} supplier(s) need register work, "
                  f"{len(queue) - undecided} settled by the screen alone:")
    for i, item in enumerate(queue, 1):
        log("triage", f"    {i}. {item['name']}  "
                      f"(sanctions {item['sanctions_score']:.2f}"
                      f"{', settled - 0 lookups' if item['settled'] else ''})")
    log("triage", f"reasoning: {reasoning}")

    state.update(
        queue=queue,
        evidence=state.get("evidence") or [],
        verdicts=state.get("verdicts") or [],
        skipped=state.get("skipped") or [],
        plan_reasoning=reasoning,
        screened=[],
    )
    return state


SCREEN_RULES = """\
You are establishing WHICH LEGAL ENTITY one supplier is. You do not decide
whether to pay them - someone else does that from what you find.

Tools, one per turn:
  tool="gleif_lookup"   name  = a company name to look up in the LEI register
  tool="web_search"     query = a question about whether this company exists
  tool="final_answer"   text  = a factual summary of what you established

Rules:
- Read the notepad first. NEVER repeat a lookup that is already on it - each
  one is rationed and a repeat costs another supplier its check.
- The sanctions screen is already on the notepad. It is free and it is done.
  Do not ask for it again.
- Start with the LEI register, under the name exactly as Procurement typed it.
- NO_RECORDS means the register answered and holds nothing. It does NOT mean
  the company is fake: an LEI is mainly required of entities trading in
  regulated financial markets, and many entirely legitimate companies have
  never needed one. When you get NO_RECORDS, the register can no longer help
  you - use web_search once to establish whether a real trading company of
  this name exists at all. That is the only way to tell a legitimate supplier
  with no LEI from a name nobody has ever heard of.
- HOW TO PHRASE A SEARCH. web_search matches an encyclopaedia and a search
  index on ENTITY NAMES, not on questions. Send the company name, optionally
  plus its country: "Almarai Company Saudi Arabia". Never send a question like
  "does Almarai Company exist?" - that returns NO_RESULTS for real companies
  and you will read a false negative as proof a genuine supplier is fake. If
  the full legal name returns nothing, the shorter trading name is worth one
  try; remember Procurement typed it by hand.
- LOOKUP_UNAVAILABLE is different again: nobody answered. Say so plainly;
  do not report it as an absence of records. NO_RESULTS from a search that
  DID run is a real finding.
- STOP as soon as the entity is characterised. A second lookup is only worth
  spending when the first one left you unable to say whether this company
  exists at all. Specifically:
    - register returned exactly one candidate named what Procurement typed
      -> DONE, both statuses are visible, spend nothing more.
    - register returned several candidates and none is an exact match -> DONE.
      A web search cannot tell you which of them Procurement meant; only the
      LEI on the invoice can. Report the ambiguity and stop.
    - register returned NO_RECORDS -> this is the one case worth a second
      lookup. Search for the name.
- Report what the tools returned, including contradictions and how many
  candidates carried the name. Never state a fact no tool returned.
"""


def _render_pad(pad: list) -> str:
    return "\n\n".join(pad) if pad else "(empty)"


class SubState(TypedDict):
    """The sub-agent's own luggage. Module scope, because LangGraph resolves
    these annotations by name and cannot see a class nested in a function."""
    brief: str
    pad: list
    action: Optional[dict]
    answer: Optional[str]
    allowance: int
    used: int
    calls: list
    done_tools: list          # the duplicate-lookup guard


def build_screener():
    """The ReAct sub-agent: reason -> act -> (loop | END).

    Same manager/worker shape as the Module 3 solution - one supplier goes in,
    the sub-agent decides which register to ask and when it has seen enough.
    There is no `for supplier in ...` anywhere in this file; the outer graph's
    loop-back edge does that.
    """

    def reason(state: SubState) -> SubState:
        left = state["allowance"] - state["used"]
        prompt = (
            f"{SCREEN_RULES}\n"
            f"Supplier under review:\n{state['brief']}\n\n"
            f"Notepad - everything established so far:\n{_render_pad(state['pad'])}\n\n"
            f"Lookups still permitted for THIS supplier: {left} "
            f"(project-wide: {MAX_LOOKUPS - BUDGET['used']} left of {MAX_LOOKUPS})\n"
            + ("You have no lookups left. You MUST use final_answer and report "
               "only what is already on the notepad.\n" if left <= 0 else "")
            + "What is your ONE next action?"
        )
        action = ask(SCREEN_LLM, prompt,
                     fallback=Screening(tool="final_answer",
                                        text="Screening model call failed; no "
                                             "conclusion could be formed from "
                                             "the evidence gathered."),
                     what="screen/reason")
        state["action"] = action.model_dump()
        return state

    def act(state: SubState) -> SubState:
        action = state.get("action") or {}
        tool = action.get("tool")

        if tool == "final_answer":
            state["answer"] = (action.get("text") or "").strip() or "(no summary)"
            return state

        arg = (action.get("name") if tool == "gleif_lookup"
               else action.get("query")) or ""

        # Guard 1: the duplicate. The model re-issues the same search with
        # slightly different wording and burns a lookup for an identical
        # answer. Prompting does not fix that reliably; a check in code does,
        # and it costs nothing from the budget.
        if tool in state["done_tools"]:
            state["pad"].append(
                f"{tool} was already used for this supplier - refused, no "
                f"budget spent. Use a DIFFERENT tool or give final_answer.")
            log("screen", f"refused duplicate {tool} (no budget spent)")
            return state

        # Guard 2: the pointless search. Once the register has returned
        # candidates, a web search cannot say which of them Procurement meant -
        # only the LEI on the invoice can. The prompt says so and the model
        # still spent a lookup searching "Siemens AG Germany" after the
        # register had already handed back ten candidates. Detectable, so
        # checked rather than argued about.
        if tool == "web_search":
            registry_answered = any(
                name == "gleif_lookup"
                and result not in (NO_RECORDS, LOOKUP_UNAVAILABLE)
                for name, _, result in state["calls"]
            )
            if registry_answered:
                state["pad"].append(
                    "web_search refused, no budget spent: the register has "
                    "already returned candidates for this supplier. A search "
                    "cannot tell you which of them Procurement meant - only "
                    "the identifier on the invoice can. Give final_answer "
                    "reporting the ambiguity.")
                log("screen", "refused a pointless web_search (no budget spent)")
                return state

        # Guard 3: the per-supplier ceiling.
        if state["used"] >= state["allowance"]:
            state["pad"].append(
                f"This supplier's allowance of {state['allowance']} lookup(s) "
                f"is spent. No further lookups. Give final_answer.")
            log("screen", "per-supplier allowance spent")
            return state

        # Guard 3: the project budget. spend() is the only thing that may
        # increment it, and it is called BEFORE the lookup, never after.
        if not spend(f"{tool}({arg[:48]!r})"):
            state["pad"].append(
                "PROJECT LOOKUP BUDGET EXHAUSTED - no lookup was made. "
                "Give final_answer reporting only what is already established.")
            log("screen", "project budget exhausted")
            return state

        LEDGER.append(f"{tool}({arg})")
        state["used"] += 1
        state["done_tools"] = state["done_tools"] + [tool]

        if tool == "gleif_lookup":
            result = gleif_lookup(arg)
        elif tool == "web_search":
            result = web_search(arg)
        else:
            result = (f"ERROR: unknown tool {tool!r}. Available: "
                      "gleif_lookup, web_search")

        # OBSERVE: if it is not written down here, the next reason() is blind.
        state["pad"].append(f"{tool}({arg!r}) returned:\n{result}")
        state["calls"] = state["calls"] + [(tool, arg, result)]
        log("screen", f"{tool}({arg!r}) -> {result.splitlines()[0][:90]}")
        return state

    def is_done(state: SubState) -> str:
        """The router. Reads only.

        Note it does NOT stop on an exhausted allowance: reason() is told, on
        the next turn, that it has none left and must give final_answer, so the
        sub-agent always gets to write up what it did find. The budget is
        enforced in act(), which is allowed to write; recursion_limit is the
        backstop if the model ignores the instruction entirely.
        """
        return "end" if state.get("answer") else "loop"

    g = StateGraph(SubState)
    g.add_node("reason", reason)
    g.add_node("act", act)
    g.set_entry_point("reason")
    g.add_edge("reason", "act")
    g.add_conditional_edges("act", is_done, {"end": END, "loop": "reason"})
    return g.compile()


SCREENER = build_screener()


def screen(state: State) -> State:
    """
    Gather evidence on the NEXT supplier in the queue.

    This hands ONE supplier to the compiled ReAct sub-agent and lets it decide
    which registry to ask and when it has seen enough. No reason/act loop is
    written here - that is what SCREENER is.
    """
    item = state["queue"][0]
    state["queue"] = state["queue"][1:]

    # ----------------------------------------------------------------------
    # THE ALLOCATION. Worked out here, at the moment of spending, rather than
    # promised up front - because how much this supplier needs depends on what
    # the earlier ones actually cost.
    #
    #   every undecided supplier keeps a RESERVED floor of one lookup, so a
    #   name near the front of the queue can never starve one at the back;
    #   a second lookup is granted only out of what is genuinely spare once
    #   those floors are honoured.
    #
    # With 7 suppliers, 1 settled by sanctions and 6 needing the register,
    # that is 6 reserved and 3 spare - which is what pays for the second
    # lookup on the two suppliers the register has nothing on.
    # ----------------------------------------------------------------------
    if item["settled"]:
        allowance = 0
    else:
        reserved_for_others = sum(1 for q in state["queue"] if not q["settled"])
        spare = MAX_LOOKUPS - BUDGET["used"] - reserved_for_others - 1
        allowance = min(MAX_LOOKUPS_PER_SUPPLIER, 1 + (1 if spare >= 1 else 0))
        allowance = min(allowance, MAX_LOOKUPS - BUDGET["used"])
    item["allowance"] = allowance

    log("screen", f"--- {item['name']}  (allowance {allowance}, "
                  f"{MAX_LOOKUPS - BUDGET['used']} left project-wide)")

    brief = (
        f"Name as Procurement typed it: {item['name']}\n"
        f"Jurisdiction: {item['jurisdiction']}   Sector: {item['sector']}\n"
        f"Why this name may be ambiguous: {item['name_risk']}\n"
        "These names were typed by hand from paper forms, so the spelling may "
        "not match the certificate of incorporation."
    )
    pad = [f"sanctions_screen({item['name']!r}) returned:\n{item['sanctions']}"]

    if allowance <= 0:
        # Nothing to run - and the reason matters to the verdict, so say which
        # of the two reasons it was rather than just "0 lookups".
        log("screen", "no register lookup: "
                      + ("settled by the sanctions screen" if item["settled"]
                         else "budget exhausted"))
        summary = (
            "No register lookup was spent, and none was needed: the sanctions "
            "screen above is a decisive match against a listed entity, which "
            "settles this supplier on its own. Whether it also holds an LEI "
            "cannot change that."
            if item["settled"] else
            "No register lookup was spent on this supplier because the "
            "project-wide lookup budget was exhausted. The sanctions screen "
            "above is the only evidence, and it is not enough to establish "
            "which legal entity this is."
        )
        calls = []
    else:
        sub = {
            "brief": brief,
            "pad": list(pad),
            "action": None,
            "answer": None,
            "allowance": item["allowance"],
            "used": 0,
            "calls": [],
            "done_tools": [],
        }
        try:
            result = SCREENER.invoke(
                sub, {"recursion_limit": 2 * (MAX_LOOKUPS_PER_SUPPLIER + 2) + 4})
        except Exception as e:                             # noqa: BLE001
            # A sub-agent that will not stop must not cost us the verdicts
            # already earned. The lookups it made are on the LEDGER and were
            # already charged to BUDGET, so report the abort honestly rather
            # than pretending the supplier was screened.
            log("screen", f"sub-agent aborted: {type(e).__name__}")
            result = {
                "answer": f"Screening was abandoned ({type(e).__name__}): the "
                          f"sub-agent did not converge on a conclusion.",
                "calls": [],
                "pad": pad,
            }

        summary = result.get("answer") or (
            "The screening sub-agent did not produce a summary. Read the raw "
            "tool output below instead.")
        calls = result.get("calls", [])
        pad = result.get("pad", pad)

    bundle = {
        **item,
        "summary": summary,
        # The RAW tool output travels to decide(), not just the sub-agent's
        # prose. A verdict must rest on what the register actually returned.
        "raw": pad,
        "calls": calls,
        "lookups": len(calls),
    }
    state["evidence"] = state["evidence"] + [bundle]
    state["screened"] = [bundle]
    log("screen", f"used {len(calls)} lookup(s): {summary[:120]}")
    return state


DECIDE_RULES = """\
You are deciding whether a finance manager may release a payment to ONE
supplier. Choose exactly one verdict and make it actionable.

  APPROVE       real, current, and identified beyond doubt -> release
  CONDITIONS    payable, but only after ONE specific thing is obtained
  REJECT        do not pay - and say why in one sentence she can repeat
  INSUFFICIENT  could not establish it - name the check that would settle it

Rules that decide this correctly. Every one of them is a real trap:

1. A register hit is NOT your supplier unless it is named what Procurement
   typed. If several different legal entities came back and NONE is an exact
   match, you cannot tell which one this is: CONDITIONS, and ask Procurement
   for the LEI or registration number printed on the supplier's invoice.
   Never pick the first or the largest candidate.

2. NO_RECORDS from the register does NOT mean the company does not exist. An
   LEI is mainly required of entities in regulated financial markets, so a
   real trading company can be absent. Separate the two cases using the other
   evidence:
     - independent evidence that it is a substantial real company -> CONDITIONS,
       requiring a different identifier (trade licence, commercial
       registration or VAT number) since no LEI exists to check.
     - no trace of it anywhere, in the register or outside it -> REJECT:
       there is nothing to pay.
   If nothing beyond the register was ever checked, you cannot tell these
   apart: INSUFFICIENT, and name the check that would.

3. A similarity score is not a verdict. {decisive:.2f} or above against a
   near-identical listed name is decisive: REJECT, because paying a listed
   entity is a criminal offence. Scores between {notable:.2f} and
   {decisive:.2f} are usually noise from shared words like "Trading" or
   "Company" - do not reject on them, but state the score, the listed name and
   the programme so a human can clear it. Below {notable:.2f}, say the screen
   was clean and move on.

4. The register reports TWO status fields and they can disagree. entity status
   ACTIVE with registration status LAPSED or RETIRED means the company is
   alive but has stopped revalidating its LEI, so the register's data is no
   longer certified current. That is not a reason to refuse an otherwise clean
   supplier, and it is not nothing either: CONDITIONS, requiring confirmation
   of current registered details - or the LEI renewed - before release.
   APPROVE needs BOTH ACTIVE and ISSUED.

5. LOOKUP_UNAVAILABLE means nobody answered. Never report it as an absence of
   records. If it is the only thing you have: INSUFFICIENT, re-run the lookup.

Write for a competent finance manager with no time and no compliance lawyer.
No hedging, no "further investigation is recommended". Every fact you state
must appear in the evidence below - if it is not there, you do not know it.
"""


def decide(state: State) -> State:
    """Turn the evidence for one supplier into one of the four verdicts."""
    bundle = state["screened"][0]
    raw = "\n\n".join(bundle["raw"])

    prompt = (
        DECIDE_RULES.format(decisive=SANCTIONS_DECISIVE, notable=SANCTIONS_NOTABLE)
        + f"\nSupplier as Procurement typed it: {bundle['name']}\n"
        + f"Jurisdiction: {bundle['jurisdiction']}   Sector: {bundle['sector']}\n"
        + f"Register lookups spent on this supplier: {bundle['lookups']}"
        + (" (none - so nothing outside the sanctions screen was checked)"
           if bundle["lookups"] == 0 else "")
        + f"\n\nWhat the tools actually returned:\n{raw}\n\n"
        + f"The screening sub-agent's summary:\n{bundle['summary']}\n\n"
        + "Give the verdict."
    )

    verdict = ask(
        VERDICT_LLM, prompt,
        fallback=Verdict(
            supplier=bundle["name"],
            verdict="INSUFFICIENT",
            reason="The evidence was gathered but the model call that turns it "
                   "into a verdict failed twice, so no decision was reached "
                   "for this supplier.",
            next_step="Re-run the desk for this supplier alone; the evidence "
                      "below was retrieved and does not need re-fetching.",
            evidence=bundle["summary"],
        ),
        what=f"decide/{bundle['name']}",
    )

    record = verdict.model_dump()
    record["supplier"] = bundle["name"]     # never let the model rename a supplier
    record["lookups"] = bundle["lookups"]
    record["sanctions_score"] = bundle["sanctions_score"]
    state["verdicts"] = state["verdicts"] + [record]
    log("decide", f"{record['verdict']:<12} {bundle['name']}")
    return state


def budget_left(state: State) -> str:
    """
    Router. Reads only - anything written here is discarded.

    Note the second clause: a supplier already settled by the free sanctions
    screen costs nothing to process, so an exhausted budget must not push it
    into the skipped list. That is exactly how a sanctioned supplier would end
    up unreported.
    """
    if not state["queue"]:
        return "memo"
    if BUDGET["used"] < MAX_LOOKUPS:
        return "next"
    if state["queue"][0]["settled"]:
        return "next"
    return "memo"


def write_memo(state: State) -> State:
    """
    The deliverable. Every supplier gets a line, INCLUDING the ones never
    checked - hiding what you skipped is the one unforgivable bug here.
    """
    # Anything still queued when the budget died is a skipped supplier. It has
    # been sanctions-screened, and nothing else.
    skipped = list(state.get("skipped") or [])
    for item in state["queue"]:
        skipped.append(item)

    total = len(state["verdicts"]) + len(skipped)
    order = {"REJECT": 0, "CONDITIONS": 1, "INSUFFICIENT": 2, "APPROVE": 3}
    verdicts = sorted(state["verdicts"], key=lambda v: order.get(v["verdict"], 9))

    def wrap(text: str, indent: int, width: int = 74) -> list[str]:
        words, lines, line = (text or "").split(), [], ""
        for w in words:
            if len(line) + len(w) + 1 > width - indent:
                lines.append(" " * indent + line)
                line = w
            else:
                line = f"{line} {w}".strip()
        if line:
            lines.append(" " * indent + line)
        return lines or [" " * indent + "(none)"]

    out: list[str] = [
        f"SUPPLIER REVIEW · Thursday payment run · {total} suppliers · "
        f"{BUDGET['used']} of {MAX_LOOKUPS} lookups used",
        "",
    ]

    for v in verdicts:
        out.append(f"  {v['verdict']:<13} {v['supplier']}")
        out += wrap(v["reason"], 16)
        out.append("")
        out += wrap(f"→ Rana: {v['next_step']}", 16)
        out += wrap(f"Evidence ({v['lookups']} lookup(s)): {v['evidence']}", 16)
        out.append("")

    if skipped:
        out.append("  NOT CHECKED (budget)")
        for item in skipped:
            out += wrap(
                f"{item['name']} — sanctions-screened (top similarity "
                f"{item['sanctions_score']:.2f}, below the "
                f"{SANCTIONS_DECISIVE:.2f} threshold), but no register lookup "
                f"was spent. Ranked last because: {item['name_risk']}. "
                f"Residual risk: accepted, not assessed.",
                16)
            out.append("")
        out.append("  These suppliers were not verified. Do not read their "
                   "absence above as approval.")
        out.append("")

    out.append(f"  PLAN · why the budget went where it did")
    out += wrap(state.get("plan_reasoning") or "(no plan reasoning recorded)", 16)
    out.append("")
    out.append(f"  LOOKUP LEDGER · {BUDGET['used']} of {MAX_LOOKUPS} spent "
               f"(sanctions screening is free and ran for all {total})")
    for i, entry in enumerate(LEDGER, 1):
        out.append(f"     {i:2}. {entry}")
    if not LEDGER:
        out.append("      (none)")

    memo = "\n".join(out)
    print("\n" + "=" * 78)
    print(memo)
    print("=" * 78)

    path = os.path.join(HERE, "MEMO.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Supplier review — Thursday payment run\n\n```\n" + memo + "\n```\n")
    print(f"\nwritten: {path}")

    state["skipped"] = skipped
    state["queue"] = []
    return state


def build_graph():
    """triage -> screen -> decide -> (loop back to screen | memo) -> END.

    The loop-back edge is the whole point: one supplier per pass through
    screen, so the budget is checked between suppliers rather than after the
    list has already been consumed.
    """
    g = StateGraph(State)
    g.add_node("triage", triage)
    g.add_node("screen", screen)
    g.add_node("decide", decide)
    g.add_node("write_memo", write_memo)

    g.set_entry_point("triage")
    g.add_conditional_edges("triage", budget_left,
                            {"next": "screen", "memo": "write_memo"})
    g.add_edge("screen", "decide")
    g.add_conditional_edges("decide", budget_left,
                            {"next": "screen", "memo": "write_memo"})
    g.add_edge("write_memo", END)
    return g.compile()


# ===========================================================================
if __name__ == "__main__":
    print("Vendor Onboarding Desk - setup check\n")

    ok = True
    request_path = os.path.join(HERE, "REQUEST.md")

    if not os.environ.get("OPENROUTER_API_KEY"):
        print("  [ ] OPENROUTER_API_KEY missing - copy .env.example to .env")
        ok = False
    else:
        print("  [x] API key found")

    try:
        gleif_lookup("Maersk A/S")
        print("  [x] gleif_lookup is implemented")
    except NotImplementedError:
        print("  [ ] gleif_lookup not written yet - run: python verify_tools.py")
        ok = False

    if not os.path.exists(request_path):
        print("  [ ] REQUEST.md not found - it should sit next to this file")
        ok = False
    else:
        print("  [x] REQUEST.md found")

    print()
    if not ok:
        print("Fix the boxes above first.")
        raise SystemExit(1)

    if "--check" in sys.argv:
        print("READY.")
        raise SystemExit(0)

    with open(request_path, encoding="utf-8") as f:
        request = f.read()

    app = build_graph()
    result = app.invoke(
        {
            "request": request,
            "queue": [],
            "evidence": [],
            "verdicts": [],
            "skipped": [],
            "plan_reasoning": "",
            "screened": [],
        },
        {"recursion_limit": 100},
    )

    n = len(result["verdicts"]) + len(result["skipped"])
    print(f"\n{n} supplier(s) accounted for: "
          f"{len(result['verdicts'])} with a verdict, "
          f"{len(result['skipped'])} skipped and named. "
          f"{BUDGET['used']} of {MAX_LOOKUPS} lookups spent.")
