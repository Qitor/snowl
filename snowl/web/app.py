"""FastAPI application for Snowl Web monitor."""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from pathlib import Path
from typing import Any

from snowl.web.monitor import RunMonitorStore


def _sse_encode(event: dict[str, Any]) -> str:
    event_id = str(event.get("event_id") or "")
    payload = json.dumps(event, ensure_ascii=False)
    lines = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append("event: runtime")
    lines.append(f"data: {payload}")
    return "\n".join(lines) + "\n\n"


def create_app(*, project_dir: str | Path, poll_interval_sec: float = 0.5):
    try:
        from fastapi import FastAPI, HTTPException, Query, Request
        from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
    except Exception as exc:  # pragma: no cover - runtime dependency guard
        raise RuntimeError("fastapi is required for web monitor. install with `pip install fastapi uvicorn`.") from exc

    store = RunMonitorStore(project_dir=project_dir)
    stop = threading.Event()

    def _poll_loop() -> None:
        while not stop.is_set():
            try:
                store.poll_once()
            except Exception:
                pass
            stop.wait(max(0.1, float(poll_interval_sec)))

    poller = threading.Thread(target=_poll_loop, daemon=True)

    app = FastAPI(title="Snowl Web Monitor", version="0.1")

    @app.on_event("startup")
    def _startup() -> None:
        poller.start()

    @app.on_event("shutdown")
    def _shutdown() -> None:
        stop.set()
        poller.join(timeout=1.0)
        store.close()

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _INDEX_HTML

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "project_dir": str(Path(project_dir).resolve())}

    @app.get("/api/experiments")
    def list_experiments() -> JSONResponse:
        return JSONResponse({"items": store.list_experiments()})

    @app.get("/api/experiments/{experiment_id}/summary")
    def experiment_summary(experiment_id: str, primary_dimension: str = Query(default="agent")) -> JSONResponse:
        summary = store.experiment_summary(experiment_id=experiment_id, primary_dimension=primary_dimension)
        return JSONResponse(summary)

    @app.get("/api/runs")
    def list_runs(experiment_id: str | None = None) -> JSONResponse:
        return JSONResponse({"items": store.list_runs(experiment_id=experiment_id)})

    @app.get("/api/runs/{run_id}/snapshot")
    def run_snapshot(run_id: str) -> JSONResponse:
        row = store.run_snapshot(run_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
        return JSONResponse(row)

    @app.get("/api/runs/{run_id}/pretask")
    def run_pretask(run_id: str, trial_key: str = Query(..., min_length=1)) -> JSONResponse:
        rows = store.get_pretask_events(run_id=run_id, trial_key=trial_key)
        return JSONResponse({"run_id": run_id, "trial_key": trial_key, "items": rows})

    @app.get("/api/runs/{run_id}/events/stream")
    async def stream_events(
        run_id: str,
        request: Request,
        last_event_id: str | None = None,
    ):
        snapshot = store.run_snapshot(run_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail=f"run not found: {run_id}")

        header_last_id = request.headers.get("last-event-id")
        cursor = header_last_id or last_event_id

        async def _gen():
            backlog = store.backfill_events(run_id=run_id, last_event_id=cursor, limit=500)
            for event in backlog:
                yield _sse_encode(event)

            q, unsubscribe = store.subscribe(run_id)
            try:
                last_keepalive = time.time()
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = q.get_nowait()
                    except queue.Empty:
                        now = time.time()
                        if now - last_keepalive >= 10.0:
                            last_keepalive = now
                            yield ": keepalive\n\n"
                        await asyncio.sleep(0.25)
                        continue
                    yield _sse_encode(event)
            finally:
                unsubscribe()

        return StreamingResponse(_gen(), media_type="text/event-stream")

    return app


_INDEX_HTML = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Snowl Web Monitor</title>
  <style>
    :root {
      --bg: #f4f8f7;
      --ink: #0f1f1d;
      --muted: #55706a;
      --card: #ffffff;
      --line: #d3e2de;
      --accent: #0b9f8a;
      --accent-2: #1276c4;
      --danger: #c0392b;
      --ok: #148f4f;
      --mono: "IBM Plex Mono", "SFMono-Regular", Consolas, monospace;
      --sans: "Space Grotesk", "Avenir Next", "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: var(--sans);
      color: var(--ink);
      background:
        radial-gradient(circle at 10% 10%, rgba(11,159,138,0.10), transparent 40%),
        radial-gradient(circle at 90% 20%, rgba(18,118,196,0.10), transparent 35%),
        var(--bg);
    }
    header {
      padding: 16px 20px;
      border-bottom: 1px solid var(--line);
      background: linear-gradient(92deg, #f8fffd, #eef6ff);
    }
    h1 { margin: 0; font-size: 22px; letter-spacing: 0.4px; }
    .sub { color: var(--muted); font-size: 13px; margin-top: 4px; }
    .grid {
      display: grid;
      grid-template-columns: 320px 1fr;
      gap: 12px;
      padding: 12px;
    }
    .card {
      border: 1px solid var(--line);
      background: var(--card);
      border-radius: 12px;
      padding: 12px;
      box-shadow: 0 4px 14px rgba(0,0,0,0.04);
    }
    .title {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: var(--muted);
      margin-bottom: 8px;
    }
    .list {
      max-height: 280px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .row {
      padding: 8px 10px;
      border-bottom: 1px dashed var(--line);
      cursor: pointer;
      font-size: 13px;
    }
    .row:hover { background: #f7fffd; }
    .row.active { background: #e9fbf6; border-left: 3px solid var(--accent); }
    .mono { font-family: var(--mono); }
    .pill {
      display: inline-block;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 11px;
      border: 1px solid var(--line);
      margin-left: 6px;
    }
    .ok { color: var(--ok); }
    .warn { color: #b9770e; }
    .err { color: var(--danger); }
    .toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 10px; }
    select, input, button {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 6px 8px;
      font-size: 13px;
      background: white;
    }
    button { cursor: pointer; background: linear-gradient(90deg, #ecfffb, #edf6ff); }
    .matrix {
      overflow: auto;
      max-height: 260px;
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    th, td { border-bottom: 1px solid var(--line); padding: 6px 8px; text-align: left; }
    th { position: sticky; top: 0; background: #f7fcfb; z-index: 1; }
    #events {
      height: 260px;
      overflow: auto;
      background: #0f1720;
      color: #d4e8ff;
      border-radius: 8px;
      padding: 8px;
      font-family: var(--mono);
      font-size: 11px;
      line-height: 1.45;
    }
    #pretask {
      max-height: 220px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px;
      background: #fafefe;
      font-family: var(--mono);
      font-size: 12px;
    }
    @media (max-width: 980px) {
      .grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Snowl Experiment Monitor</h1>
    <div class="sub">CLI 发起运行，Web 实时观察 · SSE 流式日志 · agent/benchmark 透视</div>
  </header>
  <div class="grid">
    <section class="card">
      <div class="title">Experiments</div>
      <div id="experiments" class="list"></div>
      <div style="margin-top:10px" class="title">Runs</div>
      <div id="runs" class="list"></div>
    </section>

    <section>
      <div class="card" style="margin-bottom: 12px;">
        <div class="toolbar">
          <label>Primary View</label>
          <select id="primary">
            <option value="agent">agent-first</option>
            <option value="benchmark">benchmark-first</option>
          </select>
          <span id="currentExp" class="mono"></span>
          <span id="currentRun" class="mono"></span>
        </div>
        <div class="title">Agent Ranking</div>
        <div id="ranking" class="matrix"></div>
        <div class="title" style="margin-top:8px;">Agent × Benchmark Matrix</div>
        <div id="matrix" class="matrix"></div>
      </div>

      <div class="card" style="margin-bottom: 12px;">
        <div class="title">Live Runtime Events</div>
        <div id="events"></div>
      </div>

      <div class="card">
        <div class="title">Pretask Timeline</div>
        <div class="toolbar">
          <input id="trialKey" placeholder="task::agent::variant::sample" style="min-width: 340px;" />
          <button id="loadPretask">Load</button>
        </div>
        <div id="pretask"></div>
      </div>
    </section>
  </div>

  <script>
    let selectedExperiment = "";
    let selectedRun = "";
    let eventSource = null;
    const maxLines = 2000;

    const $ = (id) => document.getElementById(id);

    function renderList(container, rows, onClick, key) {
      const node = $(container);
      node.innerHTML = "";
      rows.forEach((row) => {
        const div = document.createElement("div");
        div.className = "row" + (row[key] === (container === "experiments" ? selectedExperiment : selectedRun) ? " active" : "");
        if (container === "experiments") {
          div.innerHTML = `<span class="mono">${row.experiment_id}</span><span class="pill">runs ${row.run_count}</span><span class="pill">running ${row.running}</span>`;
        } else {
          div.innerHTML = `<span class="mono">${row.run_id}</span><span class="pill">${row.benchmark}</span><span class="pill ${row.status === "completed" ? "ok" : "warn"}">${row.status}</span>`;
        }
        div.onclick = () => onClick(row);
        node.appendChild(div);
      });
    }

    function renderTable(container, headers, rows) {
      const node = $(container);
      if (!rows.length) {
        node.innerHTML = "<div style='padding:8px;color:#55706a'>No data</div>";
        return;
      }
      const table = document.createElement("table");
      const thead = document.createElement("thead");
      const trh = document.createElement("tr");
      headers.forEach((h) => {
        const th = document.createElement("th");
        th.textContent = h;
        trh.appendChild(th);
      });
      thead.appendChild(trh);
      table.appendChild(thead);
      const tb = document.createElement("tbody");
      rows.forEach((r) => {
        const tr = document.createElement("tr");
        headers.forEach((h) => {
          const td = document.createElement("td");
          td.textContent = r[h] ?? "";
          tr.appendChild(td);
        });
        tb.appendChild(tr);
      });
      table.appendChild(tb);
      node.innerHTML = "";
      node.appendChild(table);
    }

    function appendEventLine(text) {
      const box = $("events");
      const div = document.createElement("div");
      div.textContent = text;
      box.appendChild(div);
      while (box.childElementCount > maxLines) box.removeChild(box.firstChild);
      box.scrollTop = box.scrollHeight;
    }

    async function loadExperiments() {
      const res = await fetch("/api/experiments");
      const data = await res.json();
      renderList("experiments", data.items || [], (row) => {
        selectedExperiment = row.experiment_id;
        $("currentExp").textContent = `exp=${selectedExperiment}`;
        loadSummary();
        loadRuns();
      }, "experiment_id");
      if (!selectedExperiment && data.items && data.items.length) {
        selectedExperiment = data.items[0].experiment_id;
        $("currentExp").textContent = `exp=${selectedExperiment}`;
        loadSummary();
        loadRuns();
      }
    }

    async function loadSummary() {
      if (!selectedExperiment) return;
      const primary = $("primary").value;
      const res = await fetch(`/api/experiments/${encodeURIComponent(selectedExperiment)}/summary?primary_dimension=${encodeURIComponent(primary)}`);
      const data = await res.json();
      const rankingRows = (data.agents || []).map((x) => {
        const flat = { agent_id: x.agent_id, rank_score: (x.rank_score || 0).toFixed(3) };
        Object.entries(x.metrics || {}).forEach(([k, v]) => flat[k] = Number(v).toFixed(3));
        return flat;
      });
      const rankHeaders = rankingRows.length ? Object.keys(rankingRows[0]) : ["agent_id", "rank_score"];
      renderTable("ranking", rankHeaders, rankingRows);

      const matrixRaw = data.matrix || {};
      const benchmarks = Array.from(new Set(Object.values(matrixRaw).flatMap((v) => Object.keys(v || {}))));
      const matrixRows = Object.keys(matrixRaw).sort().map((agent) => {
        const row = { agent_id: agent };
        benchmarks.forEach((b) => row[b] = matrixRaw[agent][b] ?? "");
        return row;
      });
      renderTable("matrix", ["agent_id", ...benchmarks], matrixRows);
    }

    async function loadRuns() {
      if (!selectedExperiment) return;
      const res = await fetch(`/api/runs?experiment_id=${encodeURIComponent(selectedExperiment)}`);
      const data = await res.json();
      renderList("runs", data.items || [], (row) => {
        selectedRun = row.run_id;
        $("currentRun").textContent = `run=${selectedRun}`;
        startStream();
      }, "run_id");
      if (!selectedRun && data.items && data.items.length) {
        selectedRun = data.items[0].run_id;
        $("currentRun").textContent = `run=${selectedRun}`;
        startStream();
      }
    }

    function startStream() {
      if (!selectedRun) return;
      if (eventSource) {
        eventSource.close();
        eventSource = null;
      }
      $("events").innerHTML = "";
      eventSource = new EventSource(`/api/runs/${encodeURIComponent(selectedRun)}/events/stream`);
      eventSource.onmessage = (ev) => {
        try {
          const row = JSON.parse(ev.data);
          const line = `[${row.event_id || ""}] ${row.event || "runtime"} task=${row.task_id || "-"} agent=${row.agent_id || "-"} ${row.message || ""}`;
          appendEventLine(line);
        } catch {
          appendEventLine(ev.data);
        }
      };
      eventSource.onerror = () => {
        appendEventLine("[stream] disconnected, auto-reconnecting...");
      };
    }

    async function loadPretask() {
      if (!selectedRun) return;
      const trialKey = $("trialKey").value.trim();
      if (!trialKey) return;
      const res = await fetch(`/api/runs/${encodeURIComponent(selectedRun)}/pretask?trial_key=${encodeURIComponent(trialKey)}`);
      const data = await res.json();
      const node = $("pretask");
      const lines = (data.items || []).map((x) => {
        const status = x.status || "";
        const source = x.source_event || "";
        const ec = (x.exit_code ?? "");
        return `${x.event} status=${status} exit=${ec} source=${source}`;
      });
      node.textContent = lines.join("\n") || "No pretask events";
    }

    $("primary").addEventListener("change", loadSummary);
    $("loadPretask").addEventListener("click", loadPretask);

    loadExperiments();
    setInterval(() => {
      if (!selectedExperiment) return;
      loadRuns();
      loadSummary();
    }, 5000);
  </script>
</body>
</html>
"""
