from __future__ import annotations

from pathlib import Path

from snowl.benchmarks.strongreject import StrongRejectScorer
from snowl.core import scorer as declare_scorer
from snowl.model import OpenAICompatibleChatClient
from snowl.project_config import load_project_config


@declare_scorer()
def scorer() -> StrongRejectScorer:
    project = load_project_config(Path(__file__).parent)
    if project.judge is None:
        raise RuntimeError("strongreject scorer requires judge.model in project.yml")
    return StrongRejectScorer(
        model_name=project.judge.model,
        client_factory=lambda _model_name: OpenAICompatibleChatClient(
            project.judge.config
        ),
    )
