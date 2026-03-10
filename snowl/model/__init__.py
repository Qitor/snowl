"""Model clients and configuration loaders."""

from snowl.model.base import ChatModelClient
from snowl.model.openai_compatible import (
    ModelResponse,
    OpenAICompatibleChatClient,
    OpenAICompatibleConfig,
    load_openai_compatible_config,
)
from snowl.model.project_matrix import (
    ProjectJudgeConfig,
    ProjectModelEntry,
    ProjectModelMatrix,
    ProjectProviderConfig,
    apply_project_judge_env,
    load_project_model_matrix,
)

__all__ = [
    "ChatModelClient",
    "ModelResponse",
    "OpenAICompatibleChatClient",
    "OpenAICompatibleConfig",
    "ProjectJudgeConfig",
    "ProjectModelEntry",
    "ProjectModelMatrix",
    "ProjectProviderConfig",
    "apply_project_judge_env",
    "load_openai_compatible_config",
    "load_project_model_matrix",
]
