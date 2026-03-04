from __future__ import annotations

import os

from snowl.benchmarks.strongreject import StrongRejectScorer
from snowl.core import scorer as declare_scorer
from snowl.model import OpenAICompatibleChatClient, load_openai_compatible_config


@declare_scorer()
def scorer() -> StrongRejectScorer:
    return StrongRejectScorer(
        model_name=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        client_factory=lambda _model_name: OpenAICompatibleChatClient(
            load_openai_compatible_config(env=os.environ)
        ),
    )
