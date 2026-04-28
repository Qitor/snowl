from pathlib import Path

from snowl.core import StopReason


class WorkspaceFixAgent:
    agent_id = "workspace_fix_agent"

    async def run(self, state, context, tools=None):
        _ = tools
        workspace = context.metadata.get("__snowl_workspace") or {}
        workspace_dir = Path(str(workspace.get("workspace_dir") or "."))
        target = workspace_dir / "src" / "app.py"
        target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        state.output = {
            "message": {"role": "assistant", "content": "patched src/app.py"},
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            "trace_events": [{"event": "example.patch", "path": "src/app.py"}],
        }
        state.stop_reason = StopReason.COMPLETED
        return state


agent = WorkspaceFixAgent()

