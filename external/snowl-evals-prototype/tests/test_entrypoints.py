"""Tests for snowl-evals prototype entry points and adapter registration."""
from __future__ import annotations

from unittest.mock import MagicMock


def test_strongreject_register() -> None:
    from snowl_evals.strongreject import register

    registry = MagicMock()
    register(registry)
    registry.register.assert_called_once()


def test_xstest_register() -> None:
    from snowl_evals.xstest import register

    registry = MagicMock()
    register(registry)
    registry.register.assert_called_once()


def test_wmdp_register() -> None:
    from snowl_evals.wmdp import register

    registry = MagicMock()
    register(registry)
    assert registry.register.call_count == 2  # cyber + chem


def test_wmdp_register_cyber() -> None:
    from snowl_evals.wmdp import register_cyber

    registry = MagicMock()
    register_cyber(registry)
    registry.register.assert_called_once()


def test_wmdp_register_chem() -> None:
    from snowl_evals.wmdp import register_chem

    registry = MagicMock()
    register_chem(registry)
    registry.register.assert_called_once()


def test_sec_qa_register() -> None:
    from snowl_evals.sec_qa import register

    registry = MagicMock()
    register(registry)
    assert registry.register.call_count == 2  # v1 + v2


def test_sec_qa_register_v1() -> None:
    from snowl_evals.sec_qa import register_v1

    registry = MagicMock()
    register_v1(registry)
    registry.register.assert_called_once()


def test_sec_qa_register_v2() -> None:
    from snowl_evals.sec_qa import register_v2

    registry = MagicMock()
    register_v2(registry)
    registry.register.assert_called_once()


def test_cybermetric_register() -> None:
    from snowl_evals.cybermetric import register

    registry = MagicMock()
    register(registry)
    assert registry.register.call_count == 4  # 80/500/2000/10000


def test_cybermetric_register_80() -> None:
    from snowl_evals.cybermetric import register_80

    registry = MagicMock()
    register_80(registry)
    registry.register.assert_called_once()


def test_cybermetric_register_500() -> None:
    from snowl_evals.cybermetric import register_500

    registry = MagicMock()
    register_500(registry)
    registry.register.assert_called_once()


def test_cybermetric_register_2000() -> None:
    from snowl_evals.cybermetric import register_2000

    registry = MagicMock()
    register_2000(registry)
    registry.register.assert_called_once()


def test_cybermetric_register_10000() -> None:
    from snowl_evals.cybermetric import register_10000

    registry = MagicMock()
    register_10000(registry)
    registry.register.assert_called_once()
