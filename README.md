# Agentic AI Bootcamp

This repository is a hands-on learning project for building agentic AI workflows with Python, LLMs, and lightweight orchestration frameworks. It is designed as a bootcamp-style workspace covering the foundations of autonomous agents, prompt-driven reasoning, and framework-based agent patterns.

The goal is to learn how AI agents can:
- reason through multi-step tasks
- use tools and observations to progress toward a goal
- structure work across modules and small experiments
- integrate with LLM providers such as OpenRouter

## Repository purpose

This project is intended for experimentation, study, and practical exercises in agentic systems. It includes examples of:
- building a minimal autonomous agent loop from scratch
- creating simple agents with CrewAI
- exploring LangGraph-based workflows
- generating study guides and error-help patterns from prompts and tools

## Project structure

```text
agentic-ai-bootcamp/
├── .gitignore
├── README.md
├── requirements.lock.txt
├── m1/
│   └── agent_loop.py
├── m2/
│   ├── hello-agents/
│   │   ├── hello_crewai.py
│   │   └── hello_langgraph.py
│   ├── error_helper/
│   │   ├── error_helper_crewai.py
│   │   └── error_helper_langgraph.py
│   └── study_guide/
│       ├── study_guide_crewai.py
│       ├── study_guide_langgraph.py
│       ├── study_guide_crewai_output.md
│       ├── study_guide_langgraph_output.md
│       └── README.md
└── .venv/   (local environment, not committed)
```

## Module overview

### Module 1: Autonomous agent loop

The `m1/agent_loop.py` file demonstrates a custom agent loop without a framework. It teaches the core agent pattern:
- send a prompt to the model
- parse the model's action
- use tools such as calculator or lookup
- feed results back into the conversation until a final answer is reached

This module focuses on reasoning loops, tool use, and safety constraints.

### Module 2: Agent frameworks and examples

The `m2/` folder contains lightweight experiments built with frameworks such as CrewAI and LangGraph:
- `hello-agents`: a minimal "hello agent" example
- `error_helper`: agents that help explain or troubleshoot errors
- `study_guide`: agents that generate learning guides or summaries from a topic

## Requirements

- Python 3.11+
- A valid OpenRouter API key
- Internet access to call the OpenRouter models

## Setup

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If you do not yet have a `requirements.txt` file in the root, install the necessary dependencies manually or use the lock file as a reference.

## Environment variables

Create a `.env` file in the project root:

```env
OPENROUTER_API_KEY=your_openrouter_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

You can also set the environment variable directly in your shell.

## Running examples

Run the custom agent loop:

```bash
python m1/agent_loop.py
```

Run the hello CrewAI example:

```bash
python m2/hello-agents/hello_crewai.py
```

You can also try the LangGraph and study guide variants under `m2/`.

## Notes

- Keep `.env`, virtual environments, and local caches out of version control.
- This repository is intended for learning and experimentation, not production deployment.
- The bootcamp focuses on understanding how agents reason, use tools, and coordinate steps.

## License

This repository is for educational purposes. Add a license if you plan to share it publicly beyond a learning project.

## Future ideas

Possible next steps for this repo include:
- adding a project-level dependency file
- adding more agent workflows
- documenting each module with examples and outputs
- converting experiments into reusable agent templates
