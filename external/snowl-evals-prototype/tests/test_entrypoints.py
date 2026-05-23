"""Tests for snowl-evals prototype entry points and adapter registration."""
from __future__ import annotations

from unittest.mock import MagicMock


def _make_registry():
    registry = MagicMock()
    registry.register.call_count = 0
    return registry


# -- Round 2 benchmarks --

def test_strongreject_register() -> None:
    from snowl_evals.strongreject import register
    registry = _make_registry()
    register(registry)
    registry.register.assert_called_once()


def test_xstest_register() -> None:
    from snowl_evals.xstest import register
    registry = _make_registry()
    register(registry)
    registry.register.assert_called_once()


def test_wmdp_register() -> None:
    from snowl_evals.wmdp import register
    registry = _make_registry()
    register(registry)
    assert registry.register.call_count == 2


def test_wmdp_register_cyber() -> None:
    from snowl_evals.wmdp import register_cyber
    registry = _make_registry()
    register_cyber(registry)
    registry.register.assert_called_once()


def test_wmdp_register_chem() -> None:
    from snowl_evals.wmdp import register_chem
    registry = _make_registry()
    register_chem(registry)
    registry.register.assert_called_once()


def test_sec_qa_register() -> None:
    from snowl_evals.sec_qa import register
    registry = _make_registry()
    register(registry)
    assert registry.register.call_count == 2


def test_cybermetric_register() -> None:
    from snowl_evals.cybermetric import register
    registry = _make_registry()
    register(registry)
    assert registry.register.call_count == 4


# -- Round 3 benchmarks --

def test_coconot_register() -> None:
    from snowl_evals.coconot import register
    registry = _make_registry()
    register(registry)
    registry.register.assert_called_once()


def test_mask_register() -> None:
    from snowl_evals.mask import register
    registry = _make_registry()
    register(registry)
    registry.register.assert_called_once()


def test_sevenllm_register() -> None:
    from snowl_evals.sevenllm import register
    registry = _make_registry()
    register(registry)
    assert registry.register.call_count == 2


def test_sevenllm_register_mcq_en() -> None:
    from snowl_evals.sevenllm import register_mcq_en
    registry = _make_registry()
    register_mcq_en(registry)
    registry.register.assert_called_once()


def test_sevenllm_register_mcq_zh() -> None:
    from snowl_evals.sevenllm import register_mcq_zh
    registry = _make_registry()
    register_mcq_zh(registry)
    registry.register.assert_called_once()


def test_fortress_register() -> None:
    from snowl_evals.fortress import register
    registry = _make_registry()
    register(registry)
    assert registry.register.call_count == 2


def test_fortress_register_adversarial() -> None:
    from snowl_evals.fortress import register_adversarial
    registry = _make_registry()
    register_adversarial(registry)
    registry.register.assert_called_once()


def test_fortress_register_benign() -> None:
    from snowl_evals.fortress import register_benign
    registry = _make_registry()
    register_benign(registry)
    registry.register.assert_called_once()


def test_agentharm_register() -> None:
    from snowl_evals.agentharm import register
    registry = _make_registry()
    register(registry)
    assert registry.register.call_count == 2


def test_agentharm_register_harm() -> None:
    from snowl_evals.agentharm import register_harm
    registry = _make_registry()
    register_harm(registry)
    registry.register.assert_called_once()


def test_agentharm_register_benign() -> None:
    from snowl_evals.agentharm import register_benign
    registry = _make_registry()
    register_benign(registry)
    registry.register.assert_called_once()


def test_agent_bench_os_register() -> None:
    from snowl_evals.agent_bench_os import register
    registry = _make_registry()
    register(registry)
    registry.register.assert_called_once()


def test_bfcl_register() -> None:
    from snowl_evals.bfcl import register
    registry = _make_registry()
    register(registry)
    registry.register.assert_called_once()


def test_ipi_coding_agent_register() -> None:
    from snowl_evals.ipi_coding_agent import register
    registry = _make_registry()
    register(registry)
    registry.register.assert_called_once()
