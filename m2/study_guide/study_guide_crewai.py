from __future__ import annotations

import os
import sys

from dotenv import find_dotenv, load_dotenv
from crewai import Agent, Crew, LLM, Process, Task

# Find your .env whether you run this from the repo or from your own project
# folder. Both calls are harmless if the file isn't there.
# This is boilerplate, not the lesson.
load_dotenv()                          # searches upward from this file
load_dotenv(find_dotenv(usecwd=True))  # searches upward from where you ran it

api_key = os.environ.get("OPENROUTER_API_KEY")
if not api_key:
    raise RuntimeError(
        "OPENROUTER_API_KEY not found.\n"
        "Create a file named .env in your project folder containing:\n"
        "    OPENROUTER_API_KEY=sk-or-...\n"
        "then run this script again."
    )


llm = LLM(
    model="openrouter/openai/gpt-4o-mini",
    temperature=0,
    api_key=api_key,
)


def build_crew() -> Crew:
    teacher = Agent(
        role="Study guide teacher",
        goal="Explain a complex topic clearly, give a good example, and create a beginner-friendly quiz.",
        backstory=(
            "You teach in plain language, focus on the key idea, explain common misconceptions, "
            "and make sure the final study guide is complete and beginner-friendly."
        ),
        llm=llm,
        verbose=True,
    )

    explain_task = Task(
        description="Explain {topic} in plain language for a beginner in 2-3 sentences.",
        expected_output="A short, clear explanation of the topic.",
        agent=teacher,
    )

    example_task = Task(
        description="Using the explanation above, create one practical example and one common misconception for {topic}.",
        expected_output="One example and one misconception, clearly labeled.",
        agent=teacher,
        context=[explain_task],
    )

    quiz_task = Task(
        description=(
            "Using the explanation and example above, assemble the complete study guide for {topic}. "
            "Include the explanation, the practical example and misconception, then exactly three questions "
            "followed by matching answers."
        ),
        expected_output=(
            "A complete guide with Explanation, Example and misconception, and Quiz sections."
        ),
        agent=teacher,
        context=[explain_task, example_task],
    )

    return Crew(
        agents=[teacher],
        tasks=[explain_task, example_task, quiz_task],
        process=Process.sequential,
        verbose=True,
        tracing=False,
    )


if __name__ == "__main__":
    topic = " ".join(sys.argv[1:]).strip() or "Model Context Protocol"

    crew = build_crew()
    result = crew.kickoff(inputs={"topic": topic})
    print(result)