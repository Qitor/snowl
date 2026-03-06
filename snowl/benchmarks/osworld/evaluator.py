"""OSWorld task setup and evaluator replication helpers."""

from __future__ import annotations

import importlib.util
import re
import sys
import time
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlparse

import requests

_FUNC_CACHE: dict[tuple[str, str], Callable[..., Any]] = {}


@dataclass
class _EvalContext:
    controller: Any
    vm_ip: str
    server_port: int
    cache_dir: str
    evaluator: Mapping[str, Any]
    action_history: list[Any]
    enable_proxy: bool = False

    @property
    def vm_platform(self) -> Any:
        try:
            return self.controller.get_vm_platform()
        except Exception:
            return None

    @property
    def vm_screen_size(self) -> Any:
        try:
            return self.controller.get_vm_screen_size()
        except Exception:
            return None


def _reference_root() -> Path:
    return Path(__file__).resolve().parents[3] / "references" / "OSWorld"


def _ensure_import_path() -> Path:
    ref_root = _reference_root()
    if not ref_root.exists():
        raise FileNotFoundError(f"OSWorld reference path not found: {ref_root}")
    root_str = str(ref_root.resolve())
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return ref_root


def _ensure_namespace_package(package_name: str, package_path: Path) -> types.ModuleType:
    path_str = str(package_path.resolve())
    existing = sys.modules.get(package_name)
    if existing is None:
        module = types.ModuleType(package_name)
        module.__package__ = package_name
        module.__file__ = str((package_path / "__init__.py").resolve())
        module.__path__ = [path_str]  # type: ignore[attr-defined]
        sys.modules[package_name] = module
        return module
    paths = list(getattr(existing, "__path__", []))
    if path_str not in paths:
        existing.__path__ = [path_str, *paths]  # type: ignore[attr-defined]
    return existing


def _load_module_from_file(*, module_name: str, module_file: Path) -> types.ModuleType:
    cached = sys.modules.get(module_name)
    if isinstance(cached, types.ModuleType):
        return cached
    spec = importlib.util.spec_from_file_location(module_name, str(module_file.resolve()))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load spec for {module_name} from {module_file}.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        message = str(exc)
        if "No module named 'frontend'" in message or "Directory 'static/' does not exist" in message:
            raise RuntimeError(
                "OSWorld evaluator import failed due conflicting `fitz` package. "
                "Please uninstall `fitz` and install `pymupdf`."
            ) from exc
        raise
    return module


def _load_callable(*, category: str, func_name: str) -> Callable[..., Any]:
    key = (category, func_name)
    cached = _FUNC_CACHE.get(key)
    if cached is not None:
        return cached

    ref_root = _ensure_import_path()
    base = ref_root / "desktop_env" / "evaluators" / category
    if not base.exists():
        raise FileNotFoundError(f"OSWorld evaluator category path not found: {base}")

    pattern = re.compile(rf"^\s*def\s+{re.escape(func_name)}\s*\(", re.MULTILINE)
    target_module: str | None = None
    target_file: Path | None = None
    for py_file in sorted(base.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        if pattern.search(text):
            target_module = f"desktop_env.evaluators.{category}.{py_file.stem}"
            target_file = py_file
            break
    if not target_module or target_file is None:
        raise AttributeError(f"OSWorld {category} function not found: {func_name}")

    desktop_env_root = ref_root / "desktop_env"
    evaluators_root = desktop_env_root / "evaluators"
    _ensure_namespace_package("desktop_env", desktop_env_root)
    _ensure_namespace_package("desktop_env.evaluators", evaluators_root)
    _ensure_namespace_package(f"desktop_env.evaluators.{category}", base)
    module = _load_module_from_file(module_name=target_module, module_file=target_file)
    fn = getattr(module, func_name, None)
    if not callable(fn):
        raise AttributeError(f"OSWorld {category} function not callable: {func_name}")
    _FUNC_CACHE[key] = fn
    return fn


def _load_metric(func_name: str) -> Callable[..., Any]:
    return _load_callable(category="metrics", func_name=func_name)


def _load_getter(getter_type: str) -> Callable[..., Any]:
    return _load_callable(category="getters", func_name=f"get_{getter_type}")


def resolve_eval_cache_dir(
    *,
    eval_cache_dir: str | None,
    eval_cache_root: str | Path,
    sample_id: str | None,
    task_id: str | None,
) -> Path:
    explicit = str(eval_cache_dir or "").strip()
    if explicit:
        path = Path(explicit)
    else:
        token = str(sample_id or task_id or "default")
        token = re.sub(r"[<>:\"/\\|?*\x00-\x1f]+", "_", token).strip(" ._") or "default"
        path = Path(eval_cache_root) / token
    path.mkdir(parents=True, exist_ok=True)
    return path


def _run_setup_step(*, step_type: str, parameters: Mapping[str, Any], endpoint: str) -> dict[str, Any]:
    step = str(step_type or "").strip().lower()
    params = dict(parameters or {})
    if step == "sleep":
        seconds = float(params.get("seconds", 1.0))
        time.sleep(max(0.0, seconds))
        return {"status_code": 200, "step_type": step, "slept_seconds": seconds, "ok": True}

    path_overrides = {
        "open": "/setup/open_file",
        "execute": "/setup/execute",
        "execute_with_verification": "/setup/execute_with_verification",
        "launch": "/setup/launch",
        "activate_window": "/setup/activate_window",
        "close_window": "/setup/close_window",
        "change_wallpaper": "/setup/change_wallpaper",
        "download": "/setup/download_file",
        "upload_file": "/setup/upload",
    }
    route = path_overrides.get(step, f"/setup/{step}")
    url = f"{endpoint.rstrip('/')}{route}"
    resp = requests.post(url, json=params, timeout=120)
    return {
        "status_code": int(resp.status_code),
        "step_type": step,
        "route": route,
        "ok": bool(resp.status_code == 200),
        "body": (resp.text or "")[:600],
    }


def run_setup_config(*, endpoint: str, setup_config: Sequence[Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for index, item in enumerate(setup_config, start=1):
        if not isinstance(item, Mapping):
            events.append({"index": index, "ok": False, "error": f"invalid setup item: {item!r}"})
            continue
        step_type = str(item.get("type") or "").strip()
        params = item.get("parameters")
        if not step_type or not isinstance(params, Mapping):
            events.append({"index": index, "ok": False, "error": f"invalid setup schema: {item!r}"})
            continue
        out = _run_setup_step(step_type=step_type, parameters=dict(params), endpoint=endpoint)
        out["index"] = index
        events.append(out)
        if not out.get("ok", False):
            break
    return events


def evaluate_task(
    *,
    endpoint: str,
    evaluator: Mapping[str, Any],
    action_history: Sequence[Any],
    proxy: bool = False,
    sample_id: str | None = None,
    task_id: str | None = None,
    eval_cache_root: str | Path = ".snowl/osworld_eval_cache",
    eval_cache_dir: str | None = None,
) -> dict[str, Any]:
    if not isinstance(evaluator, Mapping):
        raise ValueError("Missing evaluator config in payload.")
    if not endpoint:
        raise ValueError("Missing controller endpoint for OSWorld evaluation.")

    parsed = urlparse(endpoint)
    vm_ip = parsed.hostname or "localhost"
    server_port = int(parsed.port or 5000)

    _ensure_import_path()
    from desktop_env.controllers.python import PythonController  # type: ignore[import-not-found]

    cache_dir = resolve_eval_cache_dir(
        eval_cache_dir=eval_cache_dir,
        eval_cache_root=eval_cache_root,
        sample_id=sample_id,
        task_id=task_id,
    )
    controller = PythonController(vm_ip=vm_ip, server_port=server_port)
    history = list(action_history or [])
    env = _EvalContext(
        controller=controller,
        vm_ip=vm_ip,
        server_port=server_port,
        cache_dir=str(cache_dir),
        evaluator=dict(evaluator),
        action_history=history,
        enable_proxy=bool(proxy),
    )

    postconfig = evaluator.get("postconfig") or []
    post_events: list[dict[str, Any]] = []
    if isinstance(postconfig, Sequence) and not isinstance(postconfig, (str, bytes)):
        post_events = run_setup_config(endpoint=endpoint, setup_config=list(postconfig))

    func_cfg = evaluator.get("func")
    if func_cfg == "infeasible":
        if history:
            last_action = history[-1]
            if last_action == "FAIL" or (
                isinstance(last_action, Mapping)
                and str(last_action.get("action_type") or "").upper() == "FAIL"
            ):
                return {"event": "gui.evaluate", "score": 1.0, "simulated": False, "postconfig": post_events}
        return {"event": "gui.evaluate", "score": 0.0, "simulated": False, "postconfig": post_events}

    if history:
        last_action = history[-1]
        if last_action == "FAIL" or (
            isinstance(last_action, Mapping)
            and str(last_action.get("action_type") or "").upper() == "FAIL"
        ):
            return {"event": "gui.evaluate", "score": 0.0, "simulated": False, "postconfig": post_events}

    def _getter_from_cfg(cfg: Any) -> Callable[..., Any] | None:
        if not isinstance(cfg, Mapping):
            return None
        getter_type = str(cfg.get("type") or "").strip()
        if not getter_type:
            return None
        return _load_getter(getter_type)

    if isinstance(func_cfg, Sequence) and not isinstance(func_cfg, (str, bytes)):
        metric_fns = [_load_metric(str(x)) for x in list(func_cfg)]
        result_cfgs = list(evaluator.get("result") or [])
        expected_cfgs = list(evaluator.get("expected") or [])
        result_getters = [_getter_from_cfg(cfg) for cfg in result_cfgs]
        expected_getters = [_getter_from_cfg(cfg) for cfg in expected_cfgs]
        options_cfg = evaluator.get("options")
        if isinstance(options_cfg, Sequence) and not isinstance(options_cfg, (str, bytes)):
            metric_options = [dict(x or {}) for x in list(options_cfg)]
        else:
            metric_options = [{} for _ in metric_fns]
        metric_conj = str(evaluator.get("conj") or "and").lower()
        per_metric: list[dict[str, Any]] = []
        scores: list[float] = []
        for idx, metric in enumerate(metric_fns):
            result_cfg = result_cfgs[idx] if idx < len(result_cfgs) else {}
            result_getter = result_getters[idx] if idx < len(result_getters) else None
            expected_cfg = expected_cfgs[idx] if idx < len(expected_cfgs) else None
            expected_getter = expected_getters[idx] if idx < len(expected_getters) else None
            opts = metric_options[idx] if idx < len(metric_options) else {}
            if not callable(result_getter):
                raise ValueError(f"Missing result getter at index {idx}.")
            result_state = result_getter(env, result_cfg)
            if callable(expected_getter) and expected_cfg:
                expected_state = expected_getter(env, expected_cfg)
                score_value = float(metric(result_state, expected_state, **dict(opts or {})))
            else:
                score_value = float(metric(result_state, **dict(opts or {})))
            per_metric.append({"index": idx, "metric": getattr(metric, "__name__", str(metric)), "score": score_value})
            scores.append(score_value)
            if metric_conj == "and" and score_value == 0.0:
                return {
                    "event": "gui.evaluate",
                    "score": 0.0,
                    "simulated": False,
                    "postconfig": post_events,
                    "metrics": per_metric,
                }
            if metric_conj == "or" and score_value == 1.0:
                return {
                    "event": "gui.evaluate",
                    "score": 1.0,
                    "simulated": False,
                    "postconfig": post_events,
                    "metrics": per_metric,
                }
        final = (sum(scores) / len(scores)) if (metric_conj == "and" and scores) else (max(scores) if scores else 0.0)
        return {
            "event": "gui.evaluate",
            "score": float(final),
            "simulated": False,
            "postconfig": post_events,
            "metrics": per_metric,
        }

    metric = _load_metric(str(func_cfg))
    result_cfg = evaluator.get("result") or {}
    result_getter = _getter_from_cfg(result_cfg)
    if not callable(result_getter):
        raise ValueError("Missing result getter in evaluator config.")
    result_state = result_getter(env, result_cfg)
    expected_cfg = evaluator.get("expected")
    expected_getter = _getter_from_cfg(expected_cfg)
    options = dict(evaluator.get("options") or {})
    if callable(expected_getter) and isinstance(expected_cfg, Mapping):
        expected_state = expected_getter(env, expected_cfg)
        score = float(metric(result_state, expected_state, **options))
    else:
        score = float(metric(result_state, **options))
    return {
        "event": "gui.evaluate",
        "score": float(score),
        "simulated": False,
        "postconfig": post_events,
        "metric": getattr(metric, "__name__", str(metric)),
    }
