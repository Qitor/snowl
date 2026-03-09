# osworld-official

Official-style OSWorld example with Snowl primitives:

- `task.py`: load OSWorld tasks from `references/OSWorld/evaluation_examples`.
- `agent.py`: ReAct agent over OpenAI-compatible model.
- `scorer.py`: OSWorld benchmark scorer.
- `tool.py`: built-in GUI tool contracts.

## Run

Set env:

```bash
export OPENAI_BASE_URL="https://api.siliconflow.cn/v1/" #"https://api.openai.com/v1"
export OPENAI_API_KEY=""
export OPENAI_MODEL="Qwen/Qwen3-8B" #"gpt-4o-mini"

$env:OPENAI_BASE_URL="https://api.siliconflow.cn/v1/"
$env:OPENAI_API_KEY=""
$env:OPENAI_MODEL="Qwen/Qwen3-8B"

```


Run:

```bash
snowl eval examples/osworld-official

python -m snowl.cli bench run osworld --project examples/osworld-official --split test --limit 1 --max-trials 1 
```

Optional:

```bash
export SNOWL_OSWORLD_MAX_STEPS=15
export SNOWL_OSWORLD_TEMPERATURE=0.2
export SNOWL_OSWORLD_SAMPLE_LIMIT=1
export SNOWL_OSWORLD_RECORDING=1
export SNOWL_OSWORLD_OBSERVE_ACCESSIBILITY=0
export SNOWL_OSWORLD_OBSERVE_TERMINAL=0
```

Notes:

- Snowl will auto-prepare OSWorld VM disk on first run and cache it under `references/OSWorld/docker_vm_data`.
- Snowl adds required container capability by default (`--cap-add NET_ADMIN`) for OSWorld networking/port forwarding.
- If you run with `--max-trials > 1`, Snowl auto-allocates host ports per OSWorld trial to avoid `5000/9222/8006/8080` conflicts.
- First run may take a long time (download + boot). Keep the process running and check `run.log` for progress.
- When `SNOWL_OSWORLD_RECORDING=1`, agent recordings are saved under `.snowl/recordings`.
- Evaluator now follows task JSON `evaluator` config (official getter/metric path); if local metric deps are missing, run log will include fallback error details in `osworld.evaluate`.

## Evaluator Dependencies

To enable the full OSWorld evaluator function set, install optional dependencies:

```bash
pip install -e ".[osworld_eval]"
python -m playwright install chromium
```

Or install the benchmark-scoped minimal dependency set:

```bash
pip install -r snowl/benchmarks/osworld/requirements-eval-min.txt
python -m playwright install chromium
```

Troubleshooting:

- If evaluator import errors mention `No module named 'frontend'` or `Directory 'static/' does not exist`, you likely installed the wrong `fitz` package.
- Fix with:
  - `pip uninstall -y fitz`
  - `pip install -U pymupdf`

You can check current evaluator import readiness:

```bash
python scripts/check_osworld_eval_imports.py
python scripts/check_osworld_eval_imports.py --json
```

