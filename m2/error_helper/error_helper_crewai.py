"""
Module 2 Exercise - CrewAI STARTER

Same job as the LangGraph version. One Agent, two Tasks.

    Task 1: explain the error
    Task 2: suggest the fix, using Task 1's answer

Watch for two things while you build it:

  1. You never draw an edge. `Process.sequential` is the control flow.
  2. Task 2 gets Task 1's output through `context=[...]`, not through a
     variable you pass yourself.

Run:
    python error_helper_crewai.py        # sample 1
    python error_helper_crewai.py 2      # sample 2
"""

from __future__ import annotations

import os
import sys

from dotenv import find_dotenv, load_dotenv
from crewai import Agent, Crew, LLM, Process, Task

# Boilerplate, not the lesson. Finds your .env from either location.
load_dotenv()
load_dotenv(find_dotenv(usecwd=True))

api_key = os.environ.get("OPENROUTER_API_KEY")
if not api_key:
    raise RuntimeError(
        "OPENROUTER_API_KEY not found.\n"
        "Create a file named .env in your project folder containing:\n"
        "    OPENROUTER_API_KEY=sk-or-...\n"
        "then run this script again."
    )


# The same three errors as the LangGraph version.
SAMPLES = {
    "1": """Traceback (most recent call last):
  File "hello_langgraph.py", line 12, in <module>
    api_key=os.environ["OPENROUTER_API_KEY"],
            ~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^
KeyError: 'OPENROUTER_API_KEY'""",

    "2": """Traceback (most recent call last):
  File "study_guide.py", line 61, in <module>
    print(result["explanation"])
          ~~~~~~^^^^^^^^^^^^^^^
TypeError: 'NoneType' object is not subscriptable""",

    "3": """Traceback (most recent call last):
  File "hello_crewai.py", line 4, in <module>
    from crewai import Agent, Task, Crew, Process
ModuleNotFoundError: No module named 'crewai'""",
}


llm = LLM(
    model="openrouter/openai/gpt-4o-mini",
    temperature=0,
    api_key=api_key,
)


def build_crew() -> Crew:
    helper = Agent(
        role="Patient debugging helper",
        goal="Explain Python errors clearly and suggest practical fixes.",
        backstory=(
            "You explain errors in plain language, never guess at code you cannot see, "
            "and give concrete, practical steps to resolve the problem."
        ),
        llm=llm,
        verbose=True,
    )

    explain_task = Task(
        description=(
            "Explain this Python error in 2-3 sentences, using plain language and no jargon. "
            "Do not suggest a fix yet. The error is: {error_text}"
        ),
        expected_output="A short explanation of what went wrong, without a fix.",
        agent=helper,
    )

    fix_task = Task(
        description=(
            "Using the explanation above, suggest concrete steps to fix the problem in 1-2 sentences. "
            "Do not mention the raw traceback again."
        ),
        expected_output="A short, practical fix suggestion based on the explanation.",
        agent=helper,
        context=[explain_task],
    )

    return Crew(
        agents=[helper],
        tasks=[explain_task, fix_task],
        process=Process.sequential,
        verbose=True,
        tracing=False,
    )


if __name__ == "__main__":
    choice = sys.argv[1] if len(sys.argv) > 1 else "1"
    error_text = SAMPLES.get(choice, SAMPLES["1"])

    crew = build_crew()
    result = crew.kickoff(inputs={"error_text": error_text})

    print("\n" + "=" * 60)
    print("HOW TO FIX IT")
    print("=" * 60)
    print(result)
