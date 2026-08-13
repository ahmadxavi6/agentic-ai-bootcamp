from __future__ import annotations

import os
import sys
from typing import TypedDict

from dotenv import find_dotenv, load_dotenv
from langgraph.graph import END, StateGraph
from langchain_openai import ChatOpenAI

base_dir = os.path.dirname(__file__)
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


llm = ChatOpenAI(
    model="openai/gpt-4o-mini",
    temperature=0,
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key,
)


class StudyGuideState(TypedDict):
    topic: str
    explanation: str
    example: str
    quiz: str


def explain_topic(state: StudyGuideState) -> StudyGuideState:
    """Task 1: explain the topic in plain language."""
    response = llm.invoke(
        f"Explain {state['topic']} in plain language for a beginner."
    )
    state["explanation"] = response.content.strip()
    return state


def create_example(state: StudyGuideState) -> StudyGuideState:
    """Task 2: use the explanation to create an example and misconception."""
    prompt = (
        f"Using the topic '{state['topic']}' and the explanation below, create one clear real-world "
        "example and one common misconception. Format the result as:\n"
        "Example: ...\n"
        "Misconception: ...\n\n"
        f"Explanation:\n{state['explanation']}"
    )
    response = llm.invoke(prompt)
    state["example"] = response.content.strip()
    return state


def create_quiz(state: StudyGuideState) -> StudyGuideState:
    """Task 3: use earlier state to create three questions and answers."""
    prompt = (
        f"Based on the topic '{state['topic']}' and the explanation below, create exactly three beginner-"
        "friendly multiple-choice quiz questions\n"
        f"Explanation:\n{state['explanation']}\n\n"
        f"Example:\n{state['example']}"
    )
    response = llm.invoke(prompt)
    state["quiz"] = response.content.strip()
    return state


def build_graph():
    graph = StateGraph(StudyGuideState)
    graph.add_node("explain_topic", explain_topic)
    graph.add_node("create_example", create_example)
    graph.add_node("create_quiz", create_quiz)
    graph.set_entry_point("explain_topic")
    graph.add_edge("explain_topic", "create_example")
    graph.add_edge("create_example", "create_quiz")
    graph.add_edge("create_quiz", END)

    return graph.compile()


def run_study_guide(topic: str) -> StudyGuideState:
    app = build_graph()
    initial_state: StudyGuideState = {
        "topic": topic,
        "explanation": "",
        "example": "",
        "quiz": "",
    }
    return app.invoke(initial_state)


if __name__ == "__main__":
    topic = " ".join(sys.argv[1:]).strip() or "Model Context Protocol"

    result = run_study_guide(topic)

    print(f"# Study Guide: {result['topic']}\n")
    print("## Explanation\n", result["explanation"])
    print("\n## Example and misconception\n", result["example"])
    print("\n## Quiz\n", result["quiz"])