"""Registry command implementations."""

from __future__ import annotations


def _cmd_registry_list(*, kind: str | None = None) -> int:
    from snowl.registry import get_registry
    reg = get_registry()
    if kind == "benchmark":
        entries = reg.list_benchmarks()
    elif kind == "adapter":
        entries = reg.list_adapters()
    elif kind == "environment_provider":
        entries = reg.list_env_providers()
    else:
        entries = reg.list_all()
    for e in entries:
        desc = f": {e.description}" if e.description else ""
        print(f"[{e.kind}] {e.name}{desc}")
    if not entries:
        print("No registered components found.")
    return 0


def _cmd_registry_doctor() -> int:
    from snowl.registry import get_registry
    reg = get_registry()
    result = reg.doctor()
    for check in result.checks:
        status = "OK" if check["ok"] else "FAIL"
        print(f"  [{status}] {check.get('check', '?')}: {check.get('detail', '')}")
    if result.ok:
        print("\nAll registry checks passed.")
        return 0
    else:
        print("\nSome registry checks failed.")
        return 1


def _cmd_registry_info(name: str) -> int:
    from snowl.registry import get_registry
    reg = get_registry()
    try:
        entry = reg.info(name)
    except KeyError as exc:
        print(f"Error: {exc}")
        return 1
    print(f"Name: {entry.name}")
    print(f"Kind: {entry.kind}")
    if entry.description:
        print(f"Description: {entry.description}")
    if entry.metadata:
        for k, v in entry.metadata.items():
            print(f"  {k}: {v}")
    return 0
