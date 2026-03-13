"""Model/provider package facade for chat clients and project-level model config helpers.

Framework role:
- Exposes OpenAI-compatible client/config plus project model-matrix loaders used during eval bootstrap.

Runtime/usage wiring:
- Imported by agents, scorer model-judge logic, and CLI/eval config loading paths.

Change guardrails:
- Keep provider client exports and project-config exports in sync with `project.yml` contract.
"""

from snowl.model.base import ChatModelClient
from snowl.model.openai_compatible import (
    ModelResponse,
    OpenAICompatibleChatClient,
    OpenAICompatibleConfig,
    load_openai_compatible_config,
)
from snowl.project_config import (
    ProjectCodeConfig,
    ProjectConfig,
    ProjectEvalConfig,
    ProjectJudgeConfig,
    ProjectModelEntry,
    ProjectProviderConfig,
    ProjectRecoveryConfig,
    ProjectRuntimeConfig,
    find_project_file,
    load_project_config,
)
from snowl.model.project_matrix import (
    ProjectModelMatrix,
    apply_project_judge_env,
    load_project_model_matrix,
)

__all__ = [
    "ChatModelClient",
    "ModelResponse",
    "OpenAICompatibleChatClient",
    "OpenAICompatibleConfig",
    "ProjectCodeConfig",
    "ProjectConfig",
    "ProjectEvalConfig",
    "ProjectJudgeConfig",
    "ProjectModelEntry",
    "ProjectModelMatrix",
    "ProjectProviderConfig",
    "ProjectRecoveryConfig",
    "ProjectRuntimeConfig",
    "apply_project_judge_env",
    "find_project_file",
    "load_openai_compatible_config",
    "load_project_config",
    "load_project_model_matrix",
]
