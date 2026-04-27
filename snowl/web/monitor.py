"""Web-monitor backend store for run discovery, event ingestion, indexing, and experiment/run summaries.

Framework role:
- Consumes run artifacts and live events to provide queryable monitor state without altering runtime execution behavior.

Runtime/usage wiring:
- Used by web API handlers to serve run lists, event streams, and summary views.
- Key top-level symbols in this file: `RunState`, `RunMonitorStore`.

Change guardrails:
- Keep this layer read/index focused; runtime semantics belong to eval/runtime modules.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
import json
import queue
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable


@dataclass
class RunState:
    run_id: str
    run_dir: Path
    events_path: Path
    manifest_path: Path
    summary_path: Path
    plan_path: Path
    aggregate_path: Path
    profiling_path: Path
    event_pos: int = 0
    last_event_index: int = 0
    updated_at_ms: int = 0
    status: str = "running"
    experiment_id: str = ""
    benchmark: str = "custom"
    summary: dict[str, Any] = field(default_factory=dict)
    plan: dict[str, Any] = field(default_factory=dict)


class RunMonitorStore:
    def __init__(
        self,
        *,
        project_dir: str | Path,
        db_path: str | Path | None = None,
        max_event_buffer: int = 4000,
    ) -> None:
        self.project_dir = Path(project_dir).resolve()
        self.runs_root = self.project_dir / ".snowl" / "runs"
        self.by_run_id_dir = self.runs_root / "by_run_id"
        self.runs_root.mkdir(parents=True, exist_ok=True)

        self.db_path = Path(db_path).resolve() if db_path is not None else (self.runs_root / "web_monitor.sqlite")
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._runs: dict[str, RunState] = {}
        self._subscribers: dict[str, list[queue.Queue[dict[str, Any]]]] = defaultdict(list)
        self._buffers: dict[str, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=max(128, int(max_event_buffer)))
        )
        self._ensure_tables()

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass

    def _ensure_tables(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
              run_id TEXT PRIMARY KEY,
              experiment_id TEXT,
              benchmark TEXT,
              run_dir TEXT,
              status TEXT,
              updated_at_ms INTEGER,
              summary_json TEXT,
              plan_json TEXT,
              manifest_json TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
              run_id TEXT NOT NULL,
              event_index INTEGER NOT NULL,
              event_id TEXT NOT NULL,
              ts_ms INTEGER,
              event_name TEXT,
              trial_key TEXT,
              benchmark TEXT,
              agent_id TEXT,
              variant_id TEXT,
              task_id TEXT,
              sample_id TEXT,
              event_json TEXT NOT NULL,
              PRIMARY KEY (run_id, event_index)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_run_event_id ON events(run_id, event_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_run_trial ON events(run_id, trial_key)")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS domain_rows (
                domain TEXT PRIMARY KEY,
                capability_score REAL,
                safety_score REAL,
                risk_index REAL,
                benchmark_count INTEGER,
                model_count INTEGER,
                updated_at_ms INTEGER,
                overview_json TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS benchmark_rows (
                benchmark TEXT,
                domain TEXT,
                run_id TEXT,
                agent_id TEXT,
                variant_id TEXT,
                model TEXT,
                primary_metric REAL,
                metric_means_json TEXT,
                sample_count INTEGER,
                model_metadata_json TEXT,
                updated_at_ms INTEGER,
                PRIMARY KEY (benchmark, run_id, agent_id, variant_id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS leaderboard_rows (
                model TEXT,
                domain TEXT,
                benchmark_type TEXT,
                primary_metric_mean REAL,
                rank INTEGER,
                benchmarks_evaluated INTEGER,
                metadata_json TEXT,
                updated_at_ms INTEGER,
                PRIMARY KEY (model, domain, benchmark_type)
            )
            """
        )
        self._conn.commit()

    def _read_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def _resolve_run_dir(self, pointer: Path) -> Path | None:
        if pointer.is_symlink():
            target = pointer.resolve()
            return target if target.exists() else None
        if pointer.is_dir():
            return pointer
        try:
            raw = pointer.read_text(encoding="utf-8").strip()
        except Exception:
            return None
        if not raw:
            return None
        target = Path(raw)
        if not target.is_absolute():
            target = (pointer.parent / target).resolve()
        return target if target.exists() else None

    def _infer_experiment_id(self, run_id: str, *, manifest: dict[str, Any], profiling: dict[str, Any]) -> str:
        value = str(manifest.get("experiment_id") or "").strip()
        if value:
            return value
        run_meta = profiling.get("run") if isinstance(profiling, dict) else {}
        if isinstance(run_meta, dict):
            value = str(run_meta.get("experiment_id") or "").strip()
            if value:
                return value
        return run_id

    def _infer_benchmark(self, *, manifest: dict[str, Any], profiling: dict[str, Any]) -> str:
        run_meta = profiling.get("run") if isinstance(profiling, dict) else {}
        if isinstance(run_meta, dict):
            value = str(run_meta.get("benchmark") or "").strip().lower()
            if value:
                return value
        value = str(manifest.get("benchmark") or "").strip().lower()
        return value or "custom"

    def _upsert_run_row(self, state: RunState, *, manifest: dict[str, Any]) -> None:
        self._conn.execute(
            """
            INSERT INTO runs(run_id, experiment_id, benchmark, run_dir, status, updated_at_ms, summary_json, plan_json, manifest_json)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
              experiment_id=excluded.experiment_id,
              benchmark=excluded.benchmark,
              run_dir=excluded.run_dir,
              status=excluded.status,
              updated_at_ms=excluded.updated_at_ms,
              summary_json=excluded.summary_json,
              plan_json=excluded.plan_json,
              manifest_json=excluded.manifest_json
            """,
            (
                state.run_id,
                state.experiment_id,
                state.benchmark,
                str(state.run_dir),
                state.status,
                int(state.updated_at_ms),
                json.dumps(state.summary, ensure_ascii=False),
                json.dumps(state.plan, ensure_ascii=False),
                json.dumps(manifest, ensure_ascii=False),
            ),
        )

    def _refresh_run_metadata(self, state: RunState) -> None:
        manifest = self._read_json(state.manifest_path)
        state.summary = self._read_json(state.summary_path)
        state.plan = self._read_json(state.plan_path)
        profiling = self._read_json(state.profiling_path)

        state.experiment_id = self._infer_experiment_id(state.run_id, manifest=manifest, profiling=profiling)
        state.benchmark = self._infer_benchmark(manifest=manifest, profiling=profiling)
        state.status = "completed" if bool(state.summary) else "running"
        state.updated_at_ms = int(time.time() * 1000)
        self._upsert_run_row(state, manifest=manifest)
        self._ingest_v2_artifacts(state)

    def _ingest_v2_artifacts(self, state: RunState) -> None:
        """Read V2 risk-monitor artifacts from the run directory and upsert into domain_rows, benchmark_rows, and leaderboard_rows tables.

        Gracefully handles missing files — if none of the artifact files exist, this is a no-op.
        """
        now_ms = int(time.time() * 1000)

        # --- domain_summary.json ---
        domain_path = state.run_dir / "domain_summary.json"
        if domain_path.exists():
            try:
                data = json.loads(domain_path.read_text(encoding="utf-8"))
                rows = data.get("rows") if isinstance(data, dict) else None
                if isinstance(rows, list):
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        domain = str(row.get("domain") or "").strip()
                        if not domain:
                            continue
                        self._conn.execute(
                            """
                            INSERT INTO domain_rows(domain, capability_score, safety_score, risk_index,
                                                    benchmark_count, model_count, updated_at_ms, overview_json)
                            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(domain) DO UPDATE SET
                                capability_score=excluded.capability_score,
                                safety_score=excluded.safety_score,
                                risk_index=excluded.risk_index,
                                benchmark_count=excluded.benchmark_count,
                                model_count=excluded.model_count,
                                updated_at_ms=excluded.updated_at_ms,
                                overview_json=excluded.overview_json
                            """,
                            (
                                domain,
                                float(row.get("capability_score") or 0.0),
                                float(row.get("safety_score") or 0.0),
                                float(row.get("risk_index") or 0.0),
                                int(row.get("benchmark_count") or 0),
                                int(row.get("model_count") or 0),
                                now_ms,
                                json.dumps(row, ensure_ascii=False),
                            ),
                        )
            except Exception:
                pass

        # --- benchmark_summary.json ---
        benchmark_path = state.run_dir / "benchmark_summary.json"
        if benchmark_path.exists():
            try:
                data = json.loads(benchmark_path.read_text(encoding="utf-8"))
                rows = data.get("rows") if isinstance(data, dict) else None
                if isinstance(rows, list):
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        benchmark = str(row.get("benchmark") or "").strip()
                        agent_id = str(row.get("agent_id") or "").strip()
                        variant_id = str(row.get("variant_id") or "default").strip()
                        run_id = state.run_id
                        if not benchmark:
                            continue
                        # primary_metric_value may be stored as primary_metric_value
                        primary_metric_value = row.get("primary_metric_value")
                        if primary_metric_value is None:
                            primary_metric_value = row.get("primary_metric", 0.0)
                        metric_means = row.get("metric_means") or {}
                        model_metadata = row.get("metadata") or row.get("model_metadata") or {}
                        self._conn.execute(
                            """
                            INSERT INTO benchmark_rows(benchmark, domain, run_id, agent_id, variant_id,
                                                       model, primary_metric, metric_means_json,
                                                       sample_count, model_metadata_json, updated_at_ms)
                            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(benchmark, run_id, agent_id, variant_id) DO UPDATE SET
                                domain=excluded.domain,
                                model=excluded.model,
                                primary_metric=excluded.primary_metric,
                                metric_means_json=excluded.metric_means_json,
                                sample_count=excluded.sample_count,
                                model_metadata_json=excluded.model_metadata_json,
                                updated_at_ms=excluded.updated_at_ms
                            """,
                            (
                                benchmark,
                                str(row.get("domain") or ""),
                                run_id,
                                agent_id,
                                variant_id,
                                str(row.get("model") or ""),
                                float(primary_metric_value or 0.0),
                                json.dumps(metric_means, ensure_ascii=False),
                                int(row.get("sample_count") or 0),
                                json.dumps(model_metadata, ensure_ascii=False),
                                now_ms,
                            ),
                        )
            except Exception:
                pass

        # --- leaderboard_rows.jsonl ---
        leaderboard_path = state.run_dir / "leaderboard_rows.jsonl"
        if leaderboard_path.exists():
            try:
                with leaderboard_path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            row = json.loads(line)
                        except Exception:
                            continue
                        if not isinstance(row, dict):
                            continue
                        model = str(row.get("model") or "").strip()
                        domain = str(row.get("domain") or "").strip()
                        benchmark_type = str(row.get("benchmark_type") or "").strip()
                        if not model or not domain or not benchmark_type:
                            continue
                        metadata = row.get("metadata") or {}
                        self._conn.execute(
                            """
                            INSERT INTO leaderboard_rows(model, domain, benchmark_type,
                                                         primary_metric_mean, rank,
                                                         benchmarks_evaluated, metadata_json, updated_at_ms)
                            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(model, domain, benchmark_type) DO UPDATE SET
                                primary_metric_mean=excluded.primary_metric_mean,
                                rank=excluded.rank,
                                benchmarks_evaluated=excluded.benchmarks_evaluated,
                                metadata_json=excluded.metadata_json,
                                updated_at_ms=excluded.updated_at_ms
                            """,
                            (
                                model,
                                domain,
                                benchmark_type,
                                float(row.get("primary_metric_mean") or 0.0),
                                int(row.get("rank") or 0),
                                int(row.get("benchmarks_evaluated") or 0),
                                json.dumps(metadata, ensure_ascii=False),
                                now_ms,
                            ),
                        )
            except Exception:
                pass

    def _notify_subscribers(self, run_id: str, event: dict[str, Any]) -> None:
        subscribers = list(self._subscribers.get(run_id, []))
        if not subscribers:
            return
        for q in subscribers:
            try:
                q.put_nowait(event)
            except queue.Full:
                try:
                    _ = q.get_nowait()
                except queue.Empty:
                    pass
                try:
                    q.put_nowait(event)
                except Exception:
                    pass

    def _ingest_events(self, state: RunState) -> int:
        if not state.events_path.exists():
            return 0
        try:
            file_size = state.events_path.stat().st_size
        except Exception:
            file_size = 0
        if file_size < state.event_pos:
            state.event_pos = 0
            state.last_event_index = 0

        ingested = 0
        with state.events_path.open("r", encoding="utf-8") as fh:
            fh.seek(state.event_pos)
            while True:
                line = fh.readline()
                if not line:
                    break
                row = line.strip()
                if not row:
                    continue
                try:
                    event = json.loads(row)
                except Exception:
                    continue
                if not isinstance(event, dict):
                    continue
                event_index = int(event.get("event_index") or (state.last_event_index + 1))
                event_id = str(event.get("event_id") or f"{state.run_id}:{event_index}")
                state.last_event_index = max(state.last_event_index, event_index)
                event["event_index"] = event_index
                event["event_id"] = event_id
                event["run_id"] = state.run_id
                event_name = str(event.get("event") or "")
                trial_key = str(event.get("trial_key") or "")
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO events(
                      run_id, event_index, event_id, ts_ms, event_name, trial_key, benchmark,
                      agent_id, variant_id, task_id, sample_id, event_json
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        state.run_id,
                        event_index,
                        event_id,
                        int(event.get("ts_ms") or 0),
                        event_name,
                        trial_key,
                        str(event.get("benchmark") or ""),
                        str(event.get("agent_id") or ""),
                        str(event.get("variant_id") or ""),
                        str(event.get("task_id") or ""),
                        str(event.get("sample_id") or ""),
                        json.dumps(event, ensure_ascii=False),
                    ),
                )
                self._buffers[state.run_id].append(event)
                self._notify_subscribers(state.run_id, event)
                ingested += 1
            state.event_pos = fh.tell()
        if ingested:
            state.updated_at_ms = int(time.time() * 1000)
        return ingested

    def _iter_run_pointers(self) -> list[tuple[str, Path]]:
        out: list[tuple[str, Path]] = []
        if self.by_run_id_dir.exists():
            for entry in sorted(self.by_run_id_dir.iterdir()):
                run_dir = self._resolve_run_dir(entry)
                if run_dir is None:
                    continue
                out.append((entry.name, run_dir))
        if not out:
            for entry in sorted(self.runs_root.iterdir() if self.runs_root.exists() else []):
                if not entry.is_dir() or entry.name == "by_run_id":
                    continue
                run_id = f"run-{entry.name}"
                out.append((run_id, entry))
        return out

    def poll_once(self) -> dict[str, int]:
        with self._lock:
            discovered = 0
            ingested = 0
            for run_id, run_dir in self._iter_run_pointers():
                state = self._runs.get(run_id)
                if state is None:
                    state = RunState(
                        run_id=run_id,
                        run_dir=run_dir,
                        events_path=run_dir / "events.jsonl",
                        manifest_path=run_dir / "manifest.json",
                        summary_path=run_dir / "summary.json",
                        plan_path=run_dir / "plan.json",
                        aggregate_path=run_dir / "aggregate.json",
                        profiling_path=run_dir / "profiling.json",
                    )
                    self._runs[run_id] = state
                    discovered += 1
                elif state.run_dir != run_dir:
                    state.run_dir = run_dir
                    state.events_path = run_dir / "events.jsonl"
                    state.manifest_path = run_dir / "manifest.json"
                    state.summary_path = run_dir / "summary.json"
                    state.plan_path = run_dir / "plan.json"
                    state.aggregate_path = run_dir / "aggregate.json"
                    state.profiling_path = run_dir / "profiling.json"
                self._refresh_run_metadata(state)
                ingested += self._ingest_events(state)
            self._conn.commit()
            return {"runs": len(self._runs), "discovered": discovered, "ingested": ingested}

    def _compute_progress(self, state: RunState) -> tuple[int, int]:
        if state.summary:
            total = int(state.summary.get("total") or 0)
            return total, total
        total = int(state.plan.get("trial_count") or 0)
        row = self._conn.execute(
            "SELECT COUNT(*) AS c FROM events WHERE run_id=? AND event_name='runtime.trial.finish'",
            (state.run_id,),
        ).fetchone()
        done = int(row["c"] if row is not None else 0)
        return done, total

    def list_runs(self, *, experiment_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            rows: list[dict[str, Any]] = []
            for state in self._runs.values():
                if experiment_id and state.experiment_id != experiment_id:
                    continue
                done, total = self._compute_progress(state)
                rows.append(
                    {
                        "run_id": state.run_id,
                        "experiment_id": state.experiment_id,
                        "benchmark": state.benchmark,
                        "status": state.status,
                        "done": done,
                        "total": total,
                        "updated_at_ms": state.updated_at_ms,
                        "path": str(state.run_dir),
                    }
                )
            rows.sort(key=lambda x: x["updated_at_ms"], reverse=True)
            return rows

    def list_experiments(self) -> list[dict[str, Any]]:
        with self._lock:
            grouped: dict[str, dict[str, Any]] = {}
            for state in self._runs.values():
                key = state.experiment_id or state.run_id
                slot = grouped.setdefault(
                    key,
                    {
                        "experiment_id": key,
                        "run_count": 0,
                        "running": 0,
                        "completed": 0,
                        "updated_at_ms": 0,
                        "benchmarks": set(),
                    },
                )
                slot["run_count"] += 1
                slot["running"] += 1 if state.status == "running" else 0
                slot["completed"] += 1 if state.status == "completed" else 0
                slot["updated_at_ms"] = max(int(slot["updated_at_ms"]), int(state.updated_at_ms))
                slot["benchmarks"].add(state.benchmark)

            out: list[dict[str, Any]] = []
            for row in grouped.values():
                out.append(
                    {
                        "experiment_id": row["experiment_id"],
                        "run_count": row["run_count"],
                        "running": row["running"],
                        "completed": row["completed"],
                        "updated_at_ms": row["updated_at_ms"],
                        "benchmarks": sorted(str(x) for x in row["benchmarks"]),
                    }
                )
            out.sort(key=lambda x: x["updated_at_ms"], reverse=True)
            return out

    def run_snapshot(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            state = self._runs.get(run_id)
            if state is None:
                return None
            done, total = self._compute_progress(state)
            return {
                "run_id": state.run_id,
                "experiment_id": state.experiment_id,
                "benchmark": state.benchmark,
                "status": state.status,
                "done": done,
                "total": total,
                "summary": dict(state.summary),
                "plan": dict(state.plan),
                "updated_at_ms": state.updated_at_ms,
                "last_event_id": f"{state.run_id}:{state.last_event_index}" if state.last_event_index > 0 else None,
            }

    def _parse_event_id(self, value: str | None) -> int:
        if not value:
            return 0
        text = str(value).strip()
        if ":" in text:
            text = text.split(":")[-1]
        try:
            return max(0, int(text))
        except Exception:
            return 0

    def backfill_events(self, *, run_id: str, last_event_id: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        with self._lock:
            idx = self._parse_event_id(last_event_id)
            rows = self._conn.execute(
                """
                SELECT event_json FROM events
                WHERE run_id=? AND event_index>?
                ORDER BY event_index ASC
                LIMIT ?
                """,
                (run_id, idx, max(1, int(limit))),
            ).fetchall()
            out: list[dict[str, Any]] = []
            for row in rows:
                try:
                    parsed = json.loads(row["event_json"])
                except Exception:
                    continue
                if isinstance(parsed, dict):
                    out.append(parsed)
            return out

    def subscribe(self, run_id: str) -> tuple[queue.Queue[dict[str, Any]], Callable[[], None]]:
        q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=2048)
        with self._lock:
            self._subscribers[run_id].append(q)

        def _unsubscribe() -> None:
            with self._lock:
                lst = self._subscribers.get(run_id, [])
                if q in lst:
                    lst.remove(q)

        return q, _unsubscribe

    def get_pretask_events(self, *, run_id: str, trial_key: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT event_json FROM events
                WHERE run_id=? AND trial_key=? AND event_name LIKE 'pretask.%'
                ORDER BY event_index ASC
                """,
                (run_id, trial_key),
            ).fetchall()
            out: list[dict[str, Any]] = []
            for row in rows:
                try:
                    parsed = json.loads(row["event_json"])
                except Exception:
                    continue
                if isinstance(parsed, dict):
                    out.append(parsed)
            return out

    def experiment_summary(self, *, experiment_id: str, primary_dimension: str = "agent") -> dict[str, Any]:
        with self._lock:
            runs = [state for state in self._runs.values() if state.experiment_id == experiment_id]
            metrics_sum: dict[str, dict[str, float]] = defaultdict(dict)
            metrics_count: dict[str, dict[str, int]] = defaultdict(dict)
            matrix: dict[str, dict[str, float]] = defaultdict(dict)

            for state in runs:
                if not state.aggregate_path.exists():
                    continue
                aggregate = self._read_json(state.aggregate_path)
                by_task_agent = aggregate.get("by_task_agent") if isinstance(aggregate, dict) else {}
                if not isinstance(by_task_agent, dict):
                    continue
                for row in by_task_agent.values():
                    if not isinstance(row, dict):
                        continue
                    agent_id = str(row.get("agent_id") or "unknown")
                    metrics = row.get("metrics") or {}
                    if not isinstance(metrics, dict):
                        continue
                    primary_value = None
                    for metric_name, metric_value in metrics.items():
                        if not isinstance(metric_value, (int, float)):
                            continue
                        metrics_sum[agent_id][str(metric_name)] = float(metrics_sum[agent_id].get(str(metric_name), 0.0)) + float(metric_value)
                        metrics_count[agent_id][str(metric_name)] = int(metrics_count[agent_id].get(str(metric_name), 0)) + 1
                        if primary_value is None:
                            primary_value = float(metric_value)
                    if primary_value is not None:
                        matrix[agent_id][state.benchmark] = primary_value

            agents: list[dict[str, Any]] = []
            for agent_id in sorted(metrics_sum.keys()):
                averages: dict[str, float] = {}
                for metric_name, total in metrics_sum[agent_id].items():
                    count = max(1, int(metrics_count[agent_id].get(metric_name, 1)))
                    averages[metric_name] = total / count
                rank_score = max(averages.values()) if averages else 0.0
                agents.append({"agent_id": agent_id, "metrics": averages, "rank_score": rank_score})
            agents.sort(key=lambda x: x["rank_score"], reverse=True)

            run_rows = [
                {
                    "run_id": state.run_id,
                    "benchmark": state.benchmark,
                    "status": state.status,
                    "updated_at_ms": state.updated_at_ms,
                }
                for state in sorted(runs, key=lambda s: s.updated_at_ms, reverse=True)
            ]

            return {
                "experiment_id": experiment_id,
                "primary_dimension": primary_dimension,
                "run_count": len(runs),
                "agents": agents,
                "matrix": {k: dict(v) for k, v in matrix.items()},
                "runs": run_rows,
            }

    # -----------------------------------------------------------------------
    # V2 risk-monitor public API
    # -----------------------------------------------------------------------

    def list_domains(self) -> list[dict[str, Any]]:
        """Return all domain rows ordered by risk_index descending."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT domain, capability_score, safety_score, risk_index, "
                "benchmark_count, model_count, updated_at_ms, overview_json "
                "FROM domain_rows ORDER BY risk_index DESC"
            ).fetchall()
            out: list[dict[str, Any]] = []
            for row in rows:
                entry = {
                    "domain": row["domain"],
                    "capability_score": row["capability_score"],
                    "safety_score": row["safety_score"],
                    "risk_index": row["risk_index"],
                    "benchmark_count": row["benchmark_count"],
                    "model_count": row["model_count"],
                    "updated_at_ms": row["updated_at_ms"],
                }
                overview_json = row["overview_json"]
                if overview_json:
                    try:
                        entry["overview"] = json.loads(overview_json)
                    except Exception:
                        pass
                out.append(entry)
            return out

    def domain_overview(self, domain: str) -> dict[str, Any] | None:
        """Return a single domain overview including related benchmark rows."""
        with self._lock:
            row = self._conn.execute(
                "SELECT domain, capability_score, safety_score, risk_index, "
                "benchmark_count, model_count, updated_at_ms, overview_json "
                "FROM domain_rows WHERE domain=?",
                (domain,),
            ).fetchone()
            if row is None:
                return None
            result: dict[str, Any] = {
                "domain": row["domain"],
                "capability_score": row["capability_score"],
                "safety_score": row["safety_score"],
                "risk_index": row["risk_index"],
                "benchmark_count": row["benchmark_count"],
                "model_count": row["model_count"],
                "updated_at_ms": row["updated_at_ms"],
            }
            overview_json = row["overview_json"]
            if overview_json:
                try:
                    result["overview"] = json.loads(overview_json)
                except Exception:
                    pass
            # Fetch related benchmark rows
            bench_rows = self._conn.execute(
                "SELECT benchmark, domain, run_id, agent_id, variant_id, model, "
                "primary_metric, metric_means_json, sample_count, model_metadata_json, updated_at_ms "
                "FROM benchmark_rows WHERE domain=?",
                (domain,),
            ).fetchall()
            benchmarks: list[dict[str, Any]] = []
            for br in bench_rows:
                entry = {
                    "benchmark": br["benchmark"],
                    "domain": br["domain"],
                    "run_id": br["run_id"],
                    "agent_id": br["agent_id"],
                    "variant_id": br["variant_id"],
                    "model": br["model"],
                    "primary_metric": br["primary_metric"],
                    "sample_count": br["sample_count"],
                    "updated_at_ms": br["updated_at_ms"],
                }
                metric_means_json = br["metric_means_json"]
                if metric_means_json:
                    try:
                        entry["metric_means"] = json.loads(metric_means_json)
                    except Exception:
                        pass
                model_metadata_json = br["model_metadata_json"]
                if model_metadata_json:
                    try:
                        entry["model_metadata"] = json.loads(model_metadata_json)
                    except Exception:
                        pass
                benchmarks.append(entry)
            result["benchmarks"] = benchmarks
            return result

    def domain_leaderboard(self, domain: str, benchmark_type: str | None = None) -> list[dict[str, Any]]:
        """Return leaderboard rows filtered by domain and optionally benchmark_type, ordered by rank."""
        with self._lock:
            if benchmark_type is not None:
                rows = self._conn.execute(
                    "SELECT model, domain, benchmark_type, primary_metric_mean, rank, "
                    "benchmarks_evaluated, metadata_json, updated_at_ms "
                    "FROM leaderboard_rows WHERE domain=? AND benchmark_type=? "
                    "ORDER BY rank ASC",
                    (domain, benchmark_type),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT model, domain, benchmark_type, primary_metric_mean, rank, "
                    "benchmarks_evaluated, metadata_json, updated_at_ms "
                    "FROM leaderboard_rows WHERE domain=? "
                    "ORDER BY benchmark_type ASC, rank ASC",
                    (domain,),
                ).fetchall()
            out: list[dict[str, Any]] = []
            for row in rows:
                entry = {
                    "model": row["model"],
                    "domain": row["domain"],
                    "benchmark_type": row["benchmark_type"],
                    "primary_metric_mean": row["primary_metric_mean"],
                    "rank": row["rank"],
                    "benchmarks_evaluated": row["benchmarks_evaluated"],
                    "updated_at_ms": row["updated_at_ms"],
                }
                metadata_json = row["metadata_json"]
                if metadata_json:
                    try:
                        entry["metadata"] = json.loads(metadata_json)
                    except Exception:
                        pass
                out.append(entry)
            return out

    def list_benchmarks_with_metadata(self) -> list[dict[str, Any]]:
        """Return unique benchmarks from benchmark_rows with aggregated metadata."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT benchmark, domain, MAX(updated_at_ms) AS updated_at_ms, "
                "SUM(sample_count) AS total_samples, COUNT(*) AS row_count "
                "FROM benchmark_rows GROUP BY benchmark ORDER BY benchmark ASC"
            ).fetchall()
            out: list[dict[str, Any]] = []
            for row in rows:
                out.append({
                    "benchmark": row["benchmark"],
                    "domain": row["domain"],
                    "total_samples": row["total_samples"],
                    "row_count": row["row_count"],
                    "updated_at_ms": row["updated_at_ms"],
                })
            return out

    def benchmark_detail(self, benchmark_name: str) -> dict[str, Any] | None:
        """Return detail for a single benchmark including all its rows from benchmark_rows."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT benchmark, domain, run_id, agent_id, variant_id, model, "
                "primary_metric, metric_means_json, sample_count, model_metadata_json, updated_at_ms "
                "FROM benchmark_rows WHERE benchmark=?",
                (benchmark_name,),
            ).fetchall()
            if not rows:
                return None
            entries: list[dict[str, Any]] = []
            for row in rows:
                entry = {
                    "benchmark": row["benchmark"],
                    "domain": row["domain"],
                    "run_id": row["run_id"],
                    "agent_id": row["agent_id"],
                    "variant_id": row["variant_id"],
                    "model": row["model"],
                    "primary_metric": row["primary_metric"],
                    "sample_count": row["sample_count"],
                    "updated_at_ms": row["updated_at_ms"],
                }
                metric_means_json = row["metric_means_json"]
                if metric_means_json:
                    try:
                        entry["metric_means"] = json.loads(metric_means_json)
                    except Exception:
                        pass
                model_metadata_json = row["model_metadata_json"]
                if model_metadata_json:
                    try:
                        entry["model_metadata"] = json.loads(model_metadata_json)
                    except Exception:
                        pass
                entries.append(entry)
            return {
                "benchmark": benchmark_name,
                "domain": rows[0]["domain"],
                "rows": entries,
            }

    def benchmark_samples(self, benchmark_name: str) -> list[dict[str, Any]]:
        """Return sample cards for a benchmark by looking up its adapter from the registry."""
        try:
            from snowl.benchmarks.registry import get_default_benchmark_registry

            registry = get_default_benchmark_registry()
            adapter = registry.create(benchmark_name)
            samples: list[dict[str, Any]] = []
            if hasattr(adapter, "_iter_rows"):
                for row_index, row in enumerate(adapter._iter_rows(), start=1):
                    card = adapter.sample_card(row) if hasattr(adapter, "sample_card") else {"id": row_index}
                    if isinstance(card, dict):
                        card.setdefault("_row_index", row_index)
                    samples.append(card)
            return samples
        except Exception:
            return []
