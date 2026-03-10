# terminalbench-official

Official Terminal-Bench example using Snowl's project-level model matrix authoring.

- `task.py`: loads tasks from `references/terminal-bench/original-tasks`
- `agent.py`: builds one `TerminusOfficialAgent` per `agent_matrix.models` entry
- `scorer.py`: parses task output / pytest-style summary
- `tool.py`: terminal tool schema example

## Model authoring

`model.yml` declares one provider and the tested model sweep:

```yaml
provider:
  kind: openai_compatible
  base_url: https://api.openai.com/v1
  api_key: sk-...
  timeout: 30
  max_retries: 2

agent_matrix:
  models:
    - id: gpt4o_mini
      model: gpt-4o-mini
    - id: qwen3_32b
      model: Qwen/Qwen3-32B
```

Each model becomes its own `AgentVariant`. Snowl also isolates container trial names, compose resources, and log paths by `variant_id`, so multi-model TerminalBench runs do not collide.

## Run

```bash
snowl eval examples/terminalbench-official
```

Optional:

```bash
export SNOWL_TB_RUN_TESTS=1
```

When enabled, the agent attempts to execute each task's `run-tests.sh` and the scorer uses pytest summary signals from output and trace.
