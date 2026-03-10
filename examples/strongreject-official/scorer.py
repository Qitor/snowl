from __future__ import annotations

from pathlib import Path

from snowl.benchmarks.strongreject import StrongRejectScorer
from snowl.core import scorer as declare_scorer
from snowl.model import OpenAICompatibleChatClient, load_project_model_matrix


@declare_scorer()
def scorer() -> StrongRejectScorer:
    matrix = load_project_model_matrix(Path(__file__).parent)
    if matrix.judge is None:
        raise RuntimeError("strongreject scorer requires judge.model in model.yml")
    return StrongRejectScorer(
        model_name=matrix.judge.model,
        client_factory=lambda _model_name: OpenAICompatibleChatClient(
            matrix.judge.config
        ),
    )
