from __future__ import annotations

import json
from pathlib import Path

from snowl.web import runtime as web_runtime


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_ensure_next_runtime_installs_once_and_reuses_source_dir(monkeypatch, tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    _write_json(source_dir / "package.json", {"name": "snowl-webui", "private": True})
    _write_json(source_dir / "package-lock.json", {"name": "snowl-webui", "lockfileVersion": 3})
    (source_dir / "src").mkdir(parents=True, exist_ok=True)
    (source_dir / "src" / "index.tsx").write_text("export {};\n", encoding="utf-8")

    calls: list[tuple[list[str], str]] = []

    def _fake_run(cmd, cwd=None, check=False, capture_output=False, text=False):
        _ = check, capture_output, text
        calls.append((list(cmd), str(cwd)))
        if list(cmd) == ["npm", "ci"] and cwd:
            (Path(str(cwd)) / "node_modules").mkdir(parents=True, exist_ok=True)
        class _Done:
            stdout = "v20.11.0"
            stderr = ""
            returncode = 0
        return _Done()

    monkeypatch.setattr(web_runtime, "resolve_webui_source", lambda: (source_dir, "repo"))
    monkeypatch.setattr(web_runtime, "_snowl_version", lambda: "1.2.3")
    monkeypatch.setattr(web_runtime, "_ensure_node_available", lambda: None)
    monkeypatch.setattr(web_runtime.subprocess, "run", _fake_run)

    rt1 = web_runtime.ensure_next_runtime()
    assert rt1.app_dir == source_dir
    assert (rt1.app_dir / "package.json").exists()
    assert calls and calls[0][0] == ["npm", "ci"]
    assert (rt1.app_dir / ".deps-lock.sha256").exists()

    calls.clear()
    rt2 = web_runtime.ensure_next_runtime()
    assert rt2.app_dir == rt1.app_dir
    assert calls == []


def test_ensure_next_build_runs_only_when_missing(monkeypatch, tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    runtime = web_runtime.NextWebRuntime(app_dir=app_dir, cache_key="k", source_dir=tmp_path, source_mode="repo")

    calls: list[list[str]] = []

    def _fake_run(cmd, cwd=None, check=False):
        _ = cwd, check
        calls.append(list(cmd))
        class _Done:
            returncode = 0
        return _Done()

    monkeypatch.setattr(web_runtime.subprocess, "run", _fake_run)

    web_runtime.ensure_next_build(runtime)
    assert calls == [["npm", "run", "build"]]

    calls.clear()
    (app_dir / ".next").mkdir(parents=True, exist_ok=True)
    (app_dir / ".next" / "BUILD_ID").write_text("x", encoding="utf-8")
    (app_dir / ".next" / ".snowl-build-stamp").write_text("k", encoding="utf-8")
    web_runtime.ensure_next_build(runtime)
    assert calls == []


def test_ensure_next_build_rebuilds_when_stamp_mismatch(monkeypatch, tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    runtime = web_runtime.NextWebRuntime(app_dir=app_dir, cache_key="k-new", source_dir=tmp_path, source_mode="repo")

    calls: list[list[str]] = []

    def _fake_run(cmd, cwd=None, check=False):
        _ = cwd, check
        calls.append(list(cmd))
        (app_dir / ".next").mkdir(parents=True, exist_ok=True)
        (app_dir / ".next" / "BUILD_ID").write_text("x", encoding="utf-8")

        class _Done:
            returncode = 0

        return _Done()

    monkeypatch.setattr(web_runtime.subprocess, "run", _fake_run)

    (app_dir / ".next").mkdir(parents=True, exist_ok=True)
    (app_dir / ".next" / "BUILD_ID").write_text("x", encoding="utf-8")
    (app_dir / ".next" / ".snowl-build-stamp").write_text("k-old", encoding="utf-8")

    web_runtime.ensure_next_build(runtime)
    assert calls == [["npm", "run", "build"]]
    assert (app_dir / ".next" / ".snowl-build-stamp").read_text(encoding="utf-8").strip() == "k-new"


def test_resolve_webui_source_prefers_repo_in_auto_mode(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / "pyproject.toml").write_text("[project]\nname='snowl'\nversion='0.0.0'\n", encoding="utf-8")
    (repo_root / "snowl").mkdir(parents=True, exist_ok=True)
    repo_webui = repo_root / "webui"
    repo_webui.mkdir(parents=True, exist_ok=True)
    _write_json(repo_webui / "package.json", {"name": "repo-webui"})

    bundled = tmp_path / "bundled"
    bundled.mkdir(parents=True, exist_ok=True)
    _write_json(bundled / "package.json", {"name": "bundled-webui"})

    monkeypatch.setattr(web_runtime, "_repo_webui_dir", lambda: repo_webui)
    monkeypatch.setattr(web_runtime, "_bundled_webui_dir", lambda: bundled)
    monkeypatch.delenv("SNOWL_WEBUI_SOURCE", raising=False)

    source_dir, source_mode = web_runtime.resolve_webui_source()
    assert source_dir == repo_webui
    assert source_mode == "repo"
