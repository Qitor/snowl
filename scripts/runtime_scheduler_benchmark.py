#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Any

from snowl.eval import run_eval


def _write_synthetic_project(
    root: Path,
    *,
    sample_count: int,
    agent_sleep_sec: float,
    scorer_sleep_sec: float,
) -> Path:
    (root / "project.yml").write_text(
        textwrap.dedent(
            f"""
            project:
              name: synthetic-scheduler-benchmark
              root_dir: .

            provider:
              id: bench
              kind: openai_compatible
              base_url: https://example.com/v1
              api_key: sk-bench
              timeout: 30
              max_retries: 1

            agent_matrix:
              models:
                - id: synthetic
                  model: synthetic-model

            eval:
              benchmark: custom
              code:
                base_dir: .
                task_module: ./task.py
                agent_module: ./agent.py
                scorer_module: ./scorer.py
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    sample_lines = "\n".join(
        [f'    yield {{"id": "s{i:02d}", "input": "x{i:02d}"}}' for i in range(sample_count)]
    )
    (root / "task.py").write_text(
        (
            "from snowl.core import EnvSpec, Task\n\n"
            "def _samples():\n"
            f"{sample_lines}\n\n"
            "task = Task(\n"
            '    task_id="synthetic:test",\n'
            '    env_spec=EnvSpec(env_type="local"),\n'
            "    sample_iter_factory=_samples,\n"
            ")\n"
        ),
        encoding="utf-8",
    )
    (root / "agent.py").write_text(
        textwrap.dedent(
            f"""
            import asyncio
            from snowl.core import StopReason

            class SyntheticAgent:
                agent_id = "synthetic_agent"

                async def run(self, state, context, tools=None):
                    _ = (context, tools)
                    await asyncio.sleep({agent_sleep_sec})
                    state.output = {{
                        "message": {{"role": "assistant", "content": "ok"}},
                        "usage": {{"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}},
                        "trace_events": [],
                    }}
                    state.stop_reason = StopReason.COMPLETED
                    return state

            agent = SyntheticAgent()
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (root / "scorer.py").write_text(
        textwrap.dedent(
            f"""
            import time
            from snowl.core import Score

            class SyntheticScorer:
                scorer_id = "synthetic_scorer"

                def score(self, task_result, trace, context):
                    _ = (task_result, trace, context)
                    time.sleep({scorer_sleep_sec})
                    return {{"accuracy": Score(value=1.0)}}

            scorer = SyntheticScorer()
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return root / "project.yml"


async def _run_case(project_file: Path, *, max_running_trials: int, max_scoring_tasks: int, provider_budget: int) -> dict[str, Any]:
    started = time.perf_counter()
    result = await run_eval(
        project_file,
        renderer=None,
        max_running_trials=max_running_trials,
        max_scoring_tasks=max_scoring_tasks,
        provider_budgets={"bench": provider_budget},
    )
    elapsed = time.perf_counter() - started
    total = result.summary.total
    return {
        "wall_clock_sec": round(elapsed, 4),
        "trials": total,
        "trials_per_sec": round((total / elapsed) if elapsed > 0 else 0.0, 4),
        "artifacts_dir": result.artifacts_dir,
    }


def run_benchmark(*, sample_count: int, agent_sleep_sec: float, scorer_sleep_sec: float) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="snowl-scheduler-bench-") as tmp:
        root = Path(tmp)
        project_file = _write_synthetic_project(
            root,
            sample_count=sample_count,
            agent_sleep_sec=agent_sleep_sec,
            scorer_sleep_sec=scorer_sleep_sec,
        )
        serial = asyncio.run(_run_case(project_file, max_running_trials=1, max_scoring_tasks=1, provider_budget=1))
        tuned = asyncio.run(_run_case(project_file, max_running_trials=4, max_scoring_tasks=4, provider_budget=4))
        speedup = (
            serial["wall_clock_sec"] / tuned["wall_clock_sec"]
            if tuned["wall_clock_sec"] > 0
            else 0.0
        )
        return {
            "timestamp_ms": int(time.time() * 1000),
            "kind": "qa_synthetic",
            "sample_count": sample_count,
            "agent_sleep_sec": agent_sleep_sec,
            "scorer_sleep_sec": scorer_sleep_sec,
            "serial": serial,
            "tuned": tuned,
            "speedup": round(speedup, 4),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Snowl runtime scheduler benchmark")
    parser.add_argument("--sample-count", type=int, default=8)
    parser.add_argument("--agent-sleep-sec", type=float, default=0.05)
    parser.add_argument("--scorer-sleep-sec", type=float, default=0.05)
    parser.add_argument("--out", default="", help="Optional JSON output path.")
    args = parser.parse_args()

    report = run_benchmark(
        sample_count=args.sample_count,
        agent_sleep_sec=args.agent_sleep_sec,
        scorer_sleep_sec=args.scorer_sleep_sec,
    )
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        out_path = Path(args.out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")
        print(str(out_path))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
