"""
Module 2 Lab — STARTER (CrewAI "hello agent")
Goal: one role + one task that, given a topic, returns a one-sentence definition.

Fill in the TODOs. Notice you DESCRIBE roles/tasks — you don't wire nodes/edges.
Set your key in .env (OPENROUTER_API_KEY=sk-or-...).
"""

import os
from dotenv import find_dotenv, load_dotenv
from openai import api_key
from crewai import Agent, Task, Crew, Process, LLM
load_dotenv()                      
load_dotenv(find_dotenv(usecwd=True)) 
base_dir = os.path.dirname(__file__)


def build_crew() -> Crew:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
      raise RuntimeError("OPENROUTER_API_KEY is not set. Add it to the module .env or the shared m1/.env file.")


    llm = LLM(
        model="openai/gpt-4o-mini",
        temperature=0,
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        provider="openai",
    )

    definer = Agent(
        role="Definition Specialist",
        goal="Define a topic clearly and concisely in one sentence.",
        backstory="You are an expert at explaining concepts in crisp, accurate language.",
        verbose=True,
        llm=llm,
    )

    define_task = Task(
        description="Define {topic} in exactly one sentence.",
        expected_output="A single-sentence definition of the topic.",
        agent=definer,
    )

    return Crew(
        agents=[definer],
        tasks=[define_task],
        process=Process.sequential,
        verbose=True,
    )


if __name__ == "__main__":
    crew = build_crew()
    result = crew.kickoff(inputs={"topic": "agentic AI"})
    print(result)