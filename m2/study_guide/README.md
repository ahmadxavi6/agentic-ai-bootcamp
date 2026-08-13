# Study Guide Mini-Project (Module 2 Phase 1)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file :

with:

```env
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

## Run commands

```bash
cd /agentic-ai-bootcamp/m2/study_guide
python3 study_guide_langgraph.py "temperature in language models"
python3 study_guide_crewai.py "temperature in language models"
```

## Topic tested

- `temperature in language models`

## Generated outputs

- LangGraph output: [study_guide_langgraph_output.md](/Users/ahmad/Desktop/bootcamp/m2/study_guide/study_guide_langgraph_output.md)
- CrewAI output: [study_guide_crewai_output.md](/Users/ahmad/Desktop/bootcamp/m2/study_guide/study_guide_crewai_output.md)

## Observations

1. **What did LangGraph make explicit?**  
   LangGraph made control flow explicit: state shape, node boundaries, and edges (`explain -> example -> quiz`) are all coded directly. Data handoff is explicit through typed state fields.

2. **What did CrewAI automate or hide?**  
   CrewAI automated orchestration and context passing between tasks in a sequential pipeline. I describe tasks/agent intent, while CrewAI manages the task execution lifecycle and handoff behavior.

3. **What would I choose for this three-task pipeline, and why?**  
   For this small pipeline, I would choose CrewAI for speed and readability. If I needed stricter deterministic routing, branching, or graph-level control, I would choose LangGraph.
