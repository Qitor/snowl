"""Scorer for ToolEmu emulation eval."""

from pathlib import Path

from snowl.benchmarks.toolemu import ToolEmuScorer
from snowl.model import OpenAICompatibleChatClient, OpenAICompatibleConfig
from snowl.project_config import load_project_config


PROJECT_DIR = Path(__file__).resolve().parent
PROJECT = load_project_config(PROJECT_DIR)
TOOLEMU_SETTINGS = PROJECT.benchmark_settings("toolemu")


def _build_evaluator_config() -> OpenAICompatibleConfig:
    evaluator = TOOLEMU_SETTINGS.get("evaluator")
    if isinstance(evaluator, dict) and evaluator.get("model"):
        fallback = PROJECT.judge.config if PROJECT.judge is not None else PROJECT.models[0].config
        return OpenAICompatibleConfig(
            provider_id=str(evaluator.get("provider_id") or fallback.provider_id),
            base_url=str(evaluator.get("base_url") or fallback.base_url),
            api_key=str(evaluator.get("api_key") or fallback.api_key),
            model=str(evaluator["model"]),
            timeout=float(evaluator.get("timeout") or fallback.timeout),
            max_retries=int(evaluator.get("max_retries") or fallback.max_retries),
        )
    return PROJECT.judge.config if PROJECT.judge is not None else PROJECT.models[0].config


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def _evaluator_disable_thinking() -> bool:
    evaluator = TOOLEMU_SETTINGS.get("evaluator")
    if not isinstance(evaluator, dict):
        return False
    return _as_bool(evaluator.get("disable_thinking"))


def _build_official_generation_kwargs() -> dict:
    if not _evaluator_disable_thinking():
        return {}
    return {"chat_template_kwargs": {"enable_thinking": False}}


EVALUATOR_CONFIG = _build_evaluator_config()

scorer = ToolEmuScorer(
    use_official_evaluator=True,
    evaluator_llm=OpenAICompatibleChatClient(EVALUATOR_CONFIG),
    official_evaluator_generation_kwargs=_build_official_generation_kwargs(),
)
