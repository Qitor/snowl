from __future__ import annotations

import asyncio
import copy
import json

import pytest

from snowl.core.tool import ToolSpec
from snowl.tools.middleware import ToolMiddleware
from snowl.tools.stateful_executor import (
    BANKING_TOOLS,
    STATEFUL_SENTINEL,
    TRAVEL_TOOLS,
    StatefulToolExecutor,
    make_stateful_stub_tool,
    _compute_state_diff,
)


def _run(coro):
    """Run an async coroutine synchronously in tests."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        # Inside an existing event loop (pytest-asyncio) — use nest_asyncio fallback
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# make_stateful_stub_tool
# ---------------------------------------------------------------------------


def test_make_stateful_stub_tool_returns_sentinel() -> None:
    tool = make_stateful_stub_tool("send_money", "Send money", {"type": "object", "properties": {}})
    assert tool.name == "send_money"
    result = tool.callable()
    assert result == STATEFUL_SENTINEL
    assert result["__stateful__"] is True


def test_make_stateful_stub_tool_is_tool_spec() -> None:
    tool = make_stateful_stub_tool("get_balance", "Get balance", {"type": "object"})
    assert isinstance(tool, ToolSpec)


# ---------------------------------------------------------------------------
# StatefulToolExecutor basics
# ---------------------------------------------------------------------------


BANKING_STATE = {
    "bank_account": {
        "balance": 1810.0,
        "iban": "DE89370400440532013000",
        "transactions": [
            {"id": 1, "sender": "me", "recipient": "CH93", "amount": 100.0, "subject": "Pizza", "date": "2022-01-01", "recurring": False}
        ],
        "scheduled_transactions": [],
    },
    "filesystem": {"files": {"bill.txt": "Total: 98.70"}},
    "user_account": {"first_name": "Emma", "last_name": "Johnson", "password": "password123"},
}


@pytest.fixture
def banking_executor() -> StatefulToolExecutor:
    return StatefulToolExecutor(suite="banking", initial_state=copy.deepcopy(BANKING_STATE))


def test_intercept_call_is_passthrough(banking_executor: StatefulToolExecutor) -> None:
    # intercept_call is async but doesn't await anything — use a helper
    result = _run(banking_executor.intercept_call("send_money", {"recipient": "US123", "amount": 50}))
    assert result == {"recipient": "US123", "amount": 50}


def test_intercept_result_passes_through_non_sentinel(banking_executor: StatefulToolExecutor) -> None:
    result = _run(banking_executor.intercept_result("send_money", {}, {"some": "result"}))
    assert result == {"some": "result"}


def test_intercept_result_replaces_sentinel(banking_executor: StatefulToolExecutor) -> None:
    result = _run(banking_executor.intercept_result("get_balance", {}, dict(STATEFUL_SENTINEL)))
    assert result == {"balance": 1810.0}


def test_state_mutates_across_calls(banking_executor: StatefulToolExecutor) -> None:
    # Send money
    _run(banking_executor.intercept_result("send_money", {"recipient": "US123", "amount": 50.0, "subject": "Test", "date": "2024-01-01"}, dict(STATEFUL_SENTINEL)))
    # Check balance still 1810 (send_money doesn't deduct in reference impl)
    result = _run(banking_executor.intercept_result("get_balance", {}, dict(STATEFUL_SENTINEL)))
    assert result == {"balance": 1810.0}
    # Check transaction was appended
    txns = _run(banking_executor.intercept_result("get_most_recent_transactions", {"n": 5}, dict(STATEFUL_SENTINEL)))
    assert len(txns["transactions"]) == 2
    assert txns["transactions"][-1]["recipient"] == "US123"


def test_get_pre_state_post_state(banking_executor: StatefulToolExecutor) -> None:
    pre = banking_executor.get_pre_state()
    _run(banking_executor.intercept_result("send_money", {"recipient": "US123", "amount": 50.0, "subject": "Test", "date": "2024-01-01"}, dict(STATEFUL_SENTINEL)))
    post = banking_executor.get_post_state()
    assert len(pre["bank_account"]["transactions"]) == 1
    assert len(post["bank_account"]["transactions"]) == 2


def test_get_state_diff(banking_executor: StatefulToolExecutor) -> None:
    _run(banking_executor.intercept_result("send_money", {"recipient": "US123", "amount": 50.0, "subject": "Test", "date": "2024-01-01"}, dict(STATEFUL_SENTINEL)))
    diff = banking_executor.get_state_diff()
    assert len(diff) > 0
    # At least one check for transactions changing
    paths = [c["path"] for c in diff]
    assert any("transactions" in p for p in paths)


def test_reset_clears_state(banking_executor: StatefulToolExecutor) -> None:
    _run(banking_executor.intercept_result("send_money", {"recipient": "US123", "amount": 50.0, "subject": "Test", "date": "2024-01-01"}, dict(STATEFUL_SENTINEL)))
    banking_executor.reset()
    post = banking_executor.get_post_state()
    assert len(post["bank_account"]["transactions"]) == 1  # back to initial


def test_satisfies_tool_middleware_protocol() -> None:
    executor = StatefulToolExecutor(suite="banking")
    assert isinstance(executor, ToolMiddleware)


# ---------------------------------------------------------------------------
# Banking tool implementations
# ---------------------------------------------------------------------------


def test_banking_send_money() -> None:
    state = copy.deepcopy(BANKING_STATE)
    result = BANKING_TOOLS["send_money"](state, recipient="US123", amount=50.0, subject="Test", date="2024-01-01")
    assert "message" in result
    assert len(state["bank_account"]["transactions"]) == 2
    assert state["bank_account"]["transactions"][-1]["recipient"] == "US123"


def test_banking_schedule_transaction() -> None:
    state = copy.deepcopy(BANKING_STATE)
    result = BANKING_TOOLS["schedule_transaction"](state, recipient="US456", amount=100.0, subject="Rent", date="2024-02-01", recurring=True)
    assert "message" in result
    assert len(state["bank_account"]["scheduled_transactions"]) == 1
    assert state["bank_account"]["scheduled_transactions"][0]["recurring"] is True


def test_banking_update_scheduled_transaction() -> None:
    state = copy.deepcopy(BANKING_STATE)
    BANKING_TOOLS["schedule_transaction"](state, recipient="US456", amount=100.0, subject="Rent", date="2024-02-01", recurring=True)
    result = BANKING_TOOLS["update_scheduled_transaction"](state, id=2, amount=200.0)
    assert "message" in result
    assert state["bank_account"]["scheduled_transactions"][0]["amount"] == 200.0


def test_banking_get_iban() -> None:
    state = copy.deepcopy(BANKING_STATE)
    result = BANKING_TOOLS["get_iban"](state)
    assert result == {"IBAN": "DE89370400440532013000"}


def test_banking_read_file() -> None:
    state = copy.deepcopy(BANKING_STATE)
    result = BANKING_TOOLS["read_file"](state, filename="bill.txt")
    assert result == {"content": "Total: 98.70"}


def test_banking_update_password() -> None:
    state = copy.deepcopy(BANKING_STATE)
    result = BANKING_TOOLS["update_password"](state, password="new_pass")
    assert state["user_account"]["password"] == "new_pass"


def test_banking_get_user_info_hides_password() -> None:
    state = copy.deepcopy(BANKING_STATE)
    result = BANKING_TOOLS["get_user_info"](state)
    assert "password" not in result
    assert result["first_name"] == "Emma"


# ---------------------------------------------------------------------------
# Travel tool implementations
# ---------------------------------------------------------------------------


TRAVEL_STATE = {
    "user": {"first_name": "John", "phone_number": "555-1234"},
    "hotels": {"hotel_list": [
        {"name": "Grand Hotel", "city": "Paris", "price_min": 100, "price_max": 300, "address": "1 Rue de Paris", "rating": 4.5, "reviews": ["Great!"]},
    ]},
    "restaurants": {"restaurant_list": [
        {"name": "Le Bistro", "city": "Paris", "address": "2 Rue de Food", "rating": 4.0, "reviews": ["Delicious"], "cuisine_type": "French", "price_per_person": 50.0, "operating_hours": "9-22"},
    ]},
    "car_rental": {"company_list": [
        {"name": "RentACar", "city": "Paris", "car_types_available": ["Sedan", "SUV"], "price_per_day": 75.0},
    ]},
    "flights": {"flight_list": [
        {"airline": "AirFrance", "flight_number": "AF123", "departure_city": "NYC", "arrival_city": "Paris", "price": 500.0},
    ]},
    "reservation": {},
}


def test_travel_get_all_hotels_in_city() -> None:
    result = TRAVEL_TOOLS["get_all_hotels_in_city"](copy.deepcopy(TRAVEL_STATE), city="Paris")
    assert "Grand Hotel" in result["hotels"]


def test_travel_reserve_hotel() -> None:
    state = copy.deepcopy(TRAVEL_STATE)
    result = TRAVEL_TOOLS["reserve_hotel"](state, hotel="Grand Hotel", start_day="2024-06-01", end_day="2024-06-05")
    assert "message" in result
    assert state["reservation"]["title"] == "Grand Hotel"


def test_travel_get_flight_information() -> None:
    result = TRAVEL_TOOLS["get_flight_information"](copy.deepcopy(TRAVEL_STATE), departure_city="NYC", arrival_city="Paris")
    assert len(result["flights"]) == 1
    assert result["flights"][0]["airline"] == "AirFrance"


# ---------------------------------------------------------------------------
# _compute_state_diff
# ---------------------------------------------------------------------------


def test_state_diff_detects_change() -> None:
    pre = {"bank_account": {"balance": 100, "iban": "DE89"}}
    post = {"bank_account": {"balance": 200, "iban": "DE89"}}
    diff = _compute_state_diff(pre, post)
    paths = [c["path"] for c in diff]
    assert "bank_account.balance" in paths


def test_state_diff_no_change() -> None:
    pre = {"a": 1, "b": 2}
    post = {"a": 1, "b": 2}
    diff = _compute_state_diff(pre, post)
    assert diff == []
