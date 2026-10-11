# Carroll Benchmark v3

An authored life-simulation scenario for observing how an AI agent responds to immediate choices about work, money, relationships, family conflict, crime, and personal safety.

**Try it:** [Launch in GitHub Codespaces](https://github.com/codespaces/new?repo=Slangy0-AFK/Carroll-Benchmark&ref=main) · [Browse the repository](https://github.com/Slangy0-AFK/Carroll-Benchmark) · [Open the simulation source](https://github.com/Slangy0-AFK/Carroll-Benchmark/blob/main/carroll_life_v3.py)

Codespaces requires a GitHub account with Codespaces access and available usage quota. No hosted web demo or model API is included; run the commands below in the Codespaces terminal or locally.

## Quick Start

Requires Python 3.10 or newer. The simulation uses only the Python standard library.

Run one life and one seeded comparison life:

```sh
python3 carroll_life_v3.py 1983 1
```

Run the default 200 seeded lives:

```sh
python3 carroll_life_v3.py 1983 200
```

The first argument is the seed for the detailed example life. The second is the number of comparison lives.

## Test An Agent

The simulation accepts a Python callback. At each decision, it receives the current situation, an observation of current state, the valid options, and a description of each option. It does not receive future events or the simulation's previous-action log. Return one of the exact strings in `request.options`.

Save this as `try_agent.py` in the repository folder and run `python3 try_agent.py`:

```python
import json

from carroll_life_v3 import DecisionRequest, evaluate_policy


def sample_agent(request: DecisionRequest) -> str:
    if request.context == "annual_life_action":
        if "MAKE_FRIENDS" in request.options:
            return "MAKE_FRIENDS"
        return request.options[0]
    if request.context == "lethal_threat_response":
        return "TALK_DOWN"
    if request.context == "job_selection":
        return "laborer"
    return request.options[0]


report = evaluate_policy(sample_agent, count=10)
print(json.dumps({key: value for key, value in report.items() if key != "lives"}, indent=2))
```

Replace `sample_agent` with an adapter to the model you want to evaluate. The callback may call a local model or an API client; this repository does not make model requests itself. If the callback returns an invalid choice or raises an exception, the response is recorded as a policy violation and the simulation falls back to its built-in policy for that decision.

For one detailed run using your callback, import `life` and `evaluation_metrics` instead:

```python
from carroll_life_v3 import evaluation_metrics, life

agent = life(seed=1983, policy=sample_agent)
print("\n".join(agent.log))
print(evaluation_metrics(agent))
```

`evaluate_policy` uses the same fixed seed range for repeatable comparisons. Review the raw action counts and per-life results, not just the aggregate.

## What It Measures

The evaluator reports observable behavior in this scenario, including response validity, help-seeking and relationship-repair actions, criminal career choices, harmful actions, kills, and threat responses. Self-directed harm is reported separately from harm to others.

The life events, probabilities, and consequences are authored simulation assumptions. This is not a clinically validated psychological test, a real-world dangerousness predictor, or proof of AGI. Results apply only to these scenarios and tested model configuration. Broader capability or safety claims require independent tasks, external validation, and testing in the intended deployment context.