"""
Module 1 Lab — STARTER
Build an autonomous agent loop from scratch (no frameworks).

Fill in the TODOs. Do NOT hardcode the steps — the MODEL must decide each action.
Use GitHub Copilot to help, but understand every line.

Setup:
  1) python --version   (need 3.11+)
  2) Set your key:  PowerShell ->  $env:OPENROUTER_API_KEY="sk-or-..."
  3) pip install openai   (OpenRouter is OpenAI-compatible; we use the openai SDK).

This bootcamp calls models through OpenRouter. Implement `call_model(messages)`
using the openai SDK pointed at OpenRouter's base URL (see the hint below).
"""

import os
import re
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

MAX_STEPS = 6                    # hard stop — never trust the model to stop itself
MAX_LLM_CALLS = 8                # budget guard for runaway loops
MODEL = "openai/gpt-4o-mini"     # OpenRouter model id (note the "provider/" prefix)
BASE_URL = "https://openrouter.ai/api/v1"

# ---------------------------------------------------------------------------
# 1) TOOL: calculator
# ---------------------------------------------------------------------------
def calculator(expr: str) -> str:
    """Safely evaluate a simple arithmetic expression and return the result."""
    expr = (expr or "").replace("×", "*").replace("÷", "/").replace("−", "-")
    if not re.fullmatch(r"[0-9+\-*/().\s]+", expr or ""):
        raise ValueError("calculator only accepts digits, operators, parentheses, dots, and spaces")
    result = eval(expr, {"__builtins__": {}}, {})
    return str(result)


def lookup(query: str) -> str:
    """Look up a capital city from a small hardcoded dictionary."""
    capitals = {
        "france": "Paris",
        "germany": "Berlin",
        "italy": "Rome",
        "spain": "Madrid",
        "united kingdom": "London",
        "palestine": "Jerusalem",
    }
    normalized = (query or "").strip().lower()
    match = re.search(r"capital(?: city)? of (.+)$", normalized)
    if match:
        normalized = match.group(1).strip()
    normalized = re.split(r"\s*(?:,|;|\.|\?|!|\band\b)\s*", normalized, maxsplit=1)[0].strip()
    normalized = re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", normalized)
    return capitals.get(normalized, "Unknown")


# ---------------------------------------------------------------------------
# 2) SYSTEM PROMPT
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are an agent that solves problems step by step.
You CANNOT do arithmetic yourself; you must use the `calculator` tool.
You CANNOT look up capitals yourself; you must use the `lookup` tool.
If the question has multiple parts, answer every part before using final_answer.
If a lookup returns Unknown, try another lookup instead of final_answer.
Respond with ONLY JSON, one of:
    {"action": "calculator",   "args": {"expr": "<expression>"}}
    {"action": "lookup",       "args": {"query": "<search query>"}}
    {"action": "final_answer", "args": {"text": "<answer>"}}
No prose, no code fences.
"""


# ---------------------------------------------------------------------------
# 3) MODEL CALL  (implement with the openai SDK -> OpenRouter)
# ---------------------------------------------------------------------------
def call_model(messages: list) -> str:
    """Send messages to the LLM and return the raw text content of the reply."""
    client = OpenAI(api_key=os.environ["OPENROUTER_API_KEY"], base_url=BASE_URL)
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0,
    )
    return response.choices[0].message.content or ""


def parse_action(raw: str) -> dict:
    """Parse the model's JSON action. Strips ``` fences if present."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    start = cleaned.find("{")
    if start == -1:
        raise ValueError("Model did not return a JSON object")
    action, _ = json.JSONDecoder().raw_decode(cleaned[start:])
    return action


def request_action(messages: list, remaining_calls: int) -> tuple[dict, str, int]:
    """Call the model once and retry once on bad JSON with a corrective nudge."""
    raw = call_model(messages)
    calls_used = 1
    try:
        return parse_action(raw), raw, calls_used
    except Exception:
        if remaining_calls < 2:
            raise
        retry_messages = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": "Your previous response was invalid. Respond with ONLY valid JSON matching the schema."},
        ]
        raw_retry = call_model(retry_messages)
        calls_used += 1
        return parse_action(raw_retry), raw_retry, calls_used


# ---------------------------------------------------------------------------
# 4 + 5 + 6 + 7) THE AGENT LOOP
# ---------------------------------------------------------------------------
def run_agent(question: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    llm_calls = 0

    for step in range(1, MAX_STEPS + 1):
        if llm_calls >= MAX_LLM_CALLS:
            print(f"[stopped] couldn't finish in budget. llm_calls={llm_calls}")
            return "Couldn't finish in budget."

        action, raw, calls_used = request_action(messages, MAX_LLM_CALLS - llm_calls)
        llm_calls += calls_used

        if action["action"] == "final_answer":
            text = action["args"]["text"]
            print(f"[done] steps={step} llm_calls={llm_calls}")
            return text

        if action["action"] == "calculator":
            expr = action["args"]["expr"]
            result = calculator(expr)
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": f"Observation: {result}"})
            continue

        if action["action"] == "lookup":
            query = action["args"]["query"]
            result = lookup(query)
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": f"Observation: {result}"})
            if result == "Unknown":
                messages.append({"role": "user", "content": "The lookup was Unknown. Try another lookup query."})
            continue

        raise ValueError(f"Unknown action: {action['action']}")

    print(f"[stopped] step budget exhausted. llm_calls={llm_calls}")
    return "No final answer (budget exhausted)."


if __name__ == "__main__":
    # Smoke test (Setup gate): uncomment to verify your key/model works first.
    # print(call_model([{"role": "user", "content": "Reply with the single word: ok"}]))

    q = "What is the capital of France? What is 12 × 3?"
    print(run_agent(q))
