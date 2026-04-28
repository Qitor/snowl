from __future__ import annotations

from pathlib import Path

from snowl.runtime.workspace import RuntimeWorkspaceManager, RuntimeWorkspaceSpec, diff_workspace, snapshot_workspace


def test_runtime_workspace_materializes_files_and_diffs(tmp_path: Path) -> None:
    manager = RuntimeWorkspaceManager(
        run_id="run-1",
        trial_id="trial-1",
        task_id="task-1",
        sample_id="sample-1",
        spec=RuntimeWorkspaceSpec(
            enabled=True,
            root=str(tmp_path),
            repo_files={"src/app.py": "old", "README.md": "hello"},
        ),
    )
    session = manager.prepare()
    assert session is not None
    workspace = Path(session.workspace_dir)
    assert (workspace / "src" / "app.py").read_text(encoding="utf-8") == "old"
    (workspace / "src" / "app.py").write_text("new", encoding="utf-8")
    (workspace / "notes.txt").write_text("created", encoding="utf-8")
    (workspace / "README.md").unlink()

    after = snapshot_workspace(workspace)
    diff = diff_workspace(session.before, after)

    assert diff["added"] == ["notes.txt"]
    assert diff["modified"] == ["src/app.py"]
    assert diff["deleted"] == ["README.md"]
