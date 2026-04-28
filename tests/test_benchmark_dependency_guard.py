from __future__ import annotations

from pathlib import Path


def test_builtin_benchmarks_do_not_bridge_reference_runtimes() -> None:
    root = Path(__file__).resolve().parents[1] / "snowl" / "benchmarks"
    guarded = {"agent_bench_os", "agentdojo", "bfcl", "ipi_coding_agent", "toolemu"}
    banned = (
        "sys.path.insert",
        "references/",
        "references" + "\\",
        "from toolemu",
        "import toolemu",
        "from agentdojo",
        "import agentdojo",
        "from bfcl",
        "import bfcl",
    )
    offenders: list[str] = []
    for package in guarded:
        package_root = root / package
        if not package_root.exists():
            continue
        paths = package_root.rglob("*.py")
        for path in paths:
            rel = path.relative_to(root)
            text = path.read_text(encoding="utf-8")
            for token in banned:
                if token in text:
                    offenders.append(f"{rel}: {token}")
    assert offenders == []
