# Tutorials

Learn Snowl's core concepts step by step.

---

## Project Anatomy

Every Snowl evaluation project is a directory with four files:

```
my-project/
  project.yml    # Configuration: provider, models, benchmark, runtime
  agent.py       # Agent definition: how the agent is constructed
  task.py        # Task definition: what benchmark to load
  scorer.py      # Scorer definition: how to score agent outputs
```

### project.yml

The central configuration file. See [Project Anatomy](project-anatomy.md) for
a complete field reference.

### agent.py

Defines the agent under test. Must export an agent object (or a list of
`AgentVariant`s via `build_model_variants`). See
[Writing an Agent](writing-an-agent.md).

### task.py

Defines what benchmark samples to load. Uses a benchmark adapter to convert
dataset rows into Snowl `Task` objects. See
[Writing a Task](writing-a-task.md).

### scorer.py

Defines how agent outputs are evaluated. Returns `Score` objects keyed by metric
name. See [Writing a Scorer](writing-a-scorer.md).

---

## Core concepts

| Concept | Role |
|---------|------|
| **Task** | A unit of work: a benchmark split with its sample iterator |
| **Agent** | The system under test: receives a state, returns a state |
| **Scorer** | Evaluates agent output: returns numeric scores with explanations |
| **ToolMiddleware** | Intercepts tool calls and results for logging, emulation, or stateful execution |
| **Trial** | One (task × agent × sample) combination, planned deterministically |
| **Run** | A complete evaluation execution producing artifacts under `.snowl/runs/` |

---

## Tutorials

| Tutorial | What you'll learn |
|----------|-------------------|
| [Project Anatomy](project-anatomy.md) | Every field in `project.yml` and how the four files connect |
| [Writing an Agent](writing-an-agent.md) | Minimal agent, ReAct agent, agents with tool middleware |
| [Writing a Task](writing-a-task.md) | Loading benchmarks, filtering, custom task factories |
| [Writing a Scorer](writing-a-scorer.md) | Sync and async scorers, composable scorers, LLM judges |
| [Tool Middleware](tool-middleware.md) | The middleware protocol, built-in middlewares, custom middleware |
| [Stateful Tool Execution](stateful-tool-execution.md) | How stateful tools work, banking/travel suites, integration with agents |
