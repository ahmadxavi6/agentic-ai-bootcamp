# Study Guide: temperature in language models (LangGraph)

## Explanation
In language models, "temperature" controls how random or creative the output is. Lower values make answers more predictable and conservative, while higher values increase variety and riskier word choices. In short: low temperature favors reliability, high temperature favors creativity.

## Example and misconception
Example: If you ask for product taglines at temperature 0.2, you get safe, similar slogans; at 1.0, you get more novel and unexpected slogans.
Misconception: "Higher temperature always means better output." Actually, very high temperature can make answers less accurate or off-topic.

## Quiz
Q1: What does a low temperature setting generally do in a language model?
A) Makes responses more random
B) Makes responses more predictable
C) Prevents any variation
A1: B) Makes responses more predictable

Q2: What is a likely effect of increasing temperature?
A) Less creativity
B) More deterministic outputs
C) More diverse outputs
A2: C) More diverse outputs

Q3: Why is very high temperature sometimes a problem?
A) It can reduce factual reliability
B) It blocks token generation
C) It disables context
A3: A) It can reduce factual reliability
