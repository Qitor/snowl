"""Public package facade for common Snowl authoring/runtime imports.

Framework role:
- Re-exports frequently used contracts (core types, runtime request/outcome types, built-in agents/scorers) for user code.

Runtime/usage wiring:
- Serves as the stable import path for examples and lightweight integrations (`from snowl import ...`).

Change guardrails:
- Keep this file as a re-export surface only; avoid heavy runtime side effects at import time.
"""

__version__ = "0.1.0"

from snowl.agents import ChatAgent, ReActAgent
from snowl.core import *  # noqa: F401,F403
from snowl.envs import LocalEnv, LocalSandboxRuntime
from snowl.errors import SnowlValidationError
from snowl.model import (
    OpenAICompatibleChatClient,
    OpenAICompatibleConfig,
    load_openai_compatible_config,
)
from snowl.runtime import TrialLimits, TrialOutcome, TrialRequest, execute_trial
from snowl.scorer import includes, match, model_as_judge_json, pattern

__all__ = [
    "__version__",
    "ChatAgent",
    "LocalEnv",
    "LocalSandboxRuntime",
    "ReActAgent",
    "OpenAICompatibleChatClient",
    "OpenAICompatibleConfig",
    "SnowlValidationError",
    "TrialLimits",
    "TrialOutcome",
    "TrialRequest",
    "execute_trial",
    "load_openai_compatible_config",
    "tool",
    "includes",
    "match",
    "model_as_judge_json",
    "pattern",
]
