# Stateful Tool Execution

For benchmarks like AgentDojo where tools mutate shared state across calls,
Snowl provides `StatefulToolExecutor`.

---

## How it works

1. Stub tools return `{"__stateful__": True}` (the sentinel value)
2. `StatefulToolExecutor.intercept_result()` detects the sentinel
3. Delegates to a real Python implementation that mutates a state dict
4. Returns the actual result instead of the sentinel

This enables agents to interact with realistic, state-changing tools without
running external services.

---

## Banking example

```python
from snowl.tools.stateful_executor import StatefulToolExecutor, make_stateful_stub_tool

# Create executor with initial state
executor = StatefulToolExecutor(
    suite="banking",
    initial_state={
        "bank_account": {"balance": 1000.0, "iban": "DE89...", "transactions": []},
        "user_account": {"first_name": "Emma", "password": "pass123"},
    },
)

# Create stub tools from OpenAI schemas
stub = make_stateful_stub_tool(
    "get_balance",
    "Get account balance",
    {"type": "object", "properties": {}},
)

# Wire into ReActAgent
agent = ReActAgent(
    model_client=client,
    middlewares=[executor],
    max_steps=10,
)

# After agent runs, inspect state changes
post_state = executor.get_post_state()
state_diff = executor.get_state_diff()  # list of {path, op, value}
```

## Available suites

### Banking suite

11 tools covering financial operations:

| Tool | Description |
|------|-------------|
| `get_balance` | Query account balance |
| `get_transactions` | List recent transactions |
| `get_iban` | Get account IBAN |
| `send_money` | Transfer money to another account |
| `schedule_payment` | Schedule a future payment |
| `get_scheduled_payments` | List scheduled payments |
| `cancel_payment` | Cancel a scheduled payment |
| `read_file` | Read a file from the user's directory |
| `write_file` | Write a file to the user's directory |
| `update_user_info` | Update user account information |
| `get_user_info` | Get user account information |

### Travel suite

18 tools covering travel services:

| Tool | Description |
|------|-------------|
| `search_hotels` | Search available hotels |
| `book_hotel` | Book a hotel room |
| `cancel_hotel` | Cancel a hotel booking |
| `search_flights` | Search available flights |
| `book_flight` | Book a flight |
| `cancel_flight` | Cancel a flight booking |
| `search_restaurants` | Search restaurants |
| `book_restaurant` | Book a restaurant table |
| `cancel_restaurant` | Cancel a restaurant booking |
| `search_car_rentals` | Search car rental options |
| `book_car_rental` | Book a car rental |
| `cancel_car_rental` | Cancel a car rental |
| `get_reservation` | Get reservation details |
| `list_reservations` | List all reservations |
| `read_file` | Read a file |
| `write_file` | Write a file |
| `update_user_info` | Update user information |
| `get_user_info` | Get user information |

## Integration with AgentDojo

The `AgentDojoAgent` wraps `ReActAgent` with `StatefulToolExecutor`:

```python
from snowl.benchmarks.agentdojo.agent import AgentDojoAgent

agent = AgentDojoAgent(
    model_client=client,
    max_steps=10,
)
```

The agent automatically:

1. Extracts `suite`, `tool_schemas`, and `pre_state` from sample metadata
2. Creates stub tools matching the tool schemas
3. Initializes `StatefulToolExecutor` with the suite and pre_state
4. Records `agentdojo_post_state` and `agentdojo_state_diff` in output

## State inspection

After agent execution, inspect state changes through the executor:

```python
# Get the current state
state = executor.get_post_state()

# Get a diff from initial to current state
diff = executor.get_state_diff()
# Returns: [{"path": "bank_account.balance", "op": "changed", "value": 900.0}, ...]

# Reset state (for reuse across trials)
executor.reset_state()
```

## Scoring state transitions

Use the `StateTransitionScorer` to verify expected state changes:

```python
from snowl.scorer import state_transition

scorer = state_transition(
    metric_name="utility",
    checks=[
        {"path": "bank_account.balance", "op": "changed"},
    ],
)
```

Or use `checkpoint_score` to combine utility and security metrics:

```python
from snowl.scorer import checkpoint_score

scorer = checkpoint_score(
    metric_name="overall",
    weights={"utility": 0.5, "security": 0.5},
)
```
