from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _default_dataset_path() -> Path:
    return _project_root() / "references" / "OSWorld" / "evaluation_examples"


def _iter_example_paths(dataset_root: Path) -> list[Path]:
    test_all = dataset_root / "test_all.json"
    if test_all.exists():
        try:
            data = json.loads(test_all.read_text(encoding="utf-8"))
            out: list[Path] = []
            if isinstance(data, dict):
                for domain, ids in data.items():
                    if not isinstance(ids, list):
                        continue
                    for example_id in ids:
                        out.append(dataset_root / "examples" / str(domain) / f"{example_id}.json")
                if out:
                    return out
        except Exception:
            pass
    return sorted((dataset_root / "examples").rglob("*.json"))


def _collect_eval_symbols(dataset_root: Path) -> tuple[set[str], set[str], list[str]]:
    metric_names: set[str] = set()
    getter_types: set[str] = set()
    parse_errors: list[str] = []

    for path in _iter_example_paths(dataset_root):
        if not path.exists():
            continue
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            parse_errors.append(f"{path}: {exc}")
            continue
        evaluator = obj.get("evaluator")
        if not isinstance(evaluator, dict):
            continue

        func_cfg = evaluator.get("func")
        if isinstance(func_cfg, list):
            for item in func_cfg:
                if item is not None:
                    metric_names.add(str(item))
        elif func_cfg is not None:
            metric_names.add(str(func_cfg))

        def _collect_from_cfg(cfg: Any) -> None:
            if isinstance(cfg, list):
                for c in cfg:
                    _collect_from_cfg(c)
                return
            if isinstance(cfg, dict):
                typ = cfg.get("type")
                if typ:
                    getter_types.add(str(typ))

        _collect_from_cfg(evaluator.get("result"))
        _collect_from_cfg(evaluator.get("expected"))
    return metric_names, getter_types, parse_errors


def _find_symbol_module(base_dir: Path, symbol_name: str) -> str | None:
    pattern = re.compile(rf"^\s*def\s+{re.escape(symbol_name)}\s*\(", re.MULTILINE)
    for py_file in sorted(base_dir.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        if pattern.search(text):
            return py_file.stem
    return None


def _check_imports(ref_root: Path, metric_names: set[str], getter_types: set[str]) -> dict[str, Any]:
    sys.path.insert(0, str(ref_root))
    metrics_dir = ref_root / "desktop_env" / "evaluators" / "metrics"
    getters_dir = ref_root / "desktop_env" / "evaluators" / "getters"

    report: dict[str, Any] = {
        "metrics_total": len(metric_names),
        "getters_total": len(getter_types),
        "missing_modules": defaultdict(list),
        "missing_symbols": [],
        "import_errors": [],
        "resolved": [],
    }

    def _try_symbol(category: str, symbol_name: str) -> None:
        base_dir = metrics_dir if category == "metrics" else getters_dir
        module_stem = _find_symbol_module(base_dir, symbol_name)
        if not module_stem:
            report["missing_symbols"].append({"category": category, "symbol": symbol_name})
            return
        module_name = f"desktop_env.evaluators.{category}.{module_stem}"
        try:
            mod = importlib.import_module(module_name)
            fn = getattr(mod, symbol_name, None)
            if not callable(fn):
                report["missing_symbols"].append({"category": category, "symbol": symbol_name, "module": module_name})
                return
            report["resolved"].append({"category": category, "symbol": symbol_name, "module": module_name})
        except ModuleNotFoundError as exc:
            missing = str(exc.name or "").strip() or str(exc)
            report["missing_modules"][missing].append(
                {"category": category, "symbol": symbol_name, "module": module_name}
            )
        except Exception as exc:
            report["import_errors"].append(
                {"category": category, "symbol": symbol_name, "module": module_name, "error": str(exc)}
            )

    for metric in sorted(metric_names):
        if metric == "infeasible":
            continue
        _try_symbol("metrics", metric)
    for getter_type in sorted(getter_types):
        _try_symbol("getters", f"get_{getter_type}")

    report["missing_modules"] = dict(report["missing_modules"])
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Check OSWorld evaluator import readiness.")
    parser.add_argument(
        "--dataset",
        type=str,
        default=str(_default_dataset_path()),
        help="Path to OSWorld evaluation_examples root.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print report as JSON.",
    )
    args = parser.parse_args()

    dataset_root = Path(args.dataset)
    ref_root = _project_root() / "references" / "OSWorld"
    if not dataset_root.exists():
        print(f"dataset not found: {dataset_root}")
        return 2
    if not ref_root.exists():
        print(f"reference not found: {ref_root}")
        return 2

    metric_names, getter_types, parse_errors = _collect_eval_symbols(dataset_root)
    report = _check_imports(ref_root, metric_names, getter_types)
    report["dataset"] = str(dataset_root)
    report["reference_root"] = str(ref_root)
    report["parse_errors"] = parse_errors

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(f"dataset={report['dataset']}")
    print(f"metrics={report['metrics_total']} getters={report['getters_total']}")
    print(f"resolved={len(report['resolved'])}")
    print(f"missing_symbol_defs={len(report['missing_symbols'])}")
    print(f"import_errors={len(report['import_errors'])}")
    print(f"missing_modules={len(report['missing_modules'])}")
    for name, users in sorted(report["missing_modules"].items(), key=lambda kv: (-len(kv[1]), kv[0])):
        print(f"- missing module '{name}': {len(users)} symbol(s)")
    if parse_errors:
        print(f"json_parse_errors={len(parse_errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
