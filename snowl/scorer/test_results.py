"""Reusable unit-test-based scorers (e.g., pytest summary parsing)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from snowl.core import Score, ScoreContext, TaskResult


class UnitTestStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class PytestTestStatus(str, Enum):
    UNKNOWN = "unknown"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    XFAIL = "xfail"
    XPASS = "xpass"
    ERROR = "error"

    def to_test_status(self) -> UnitTestStatus:
        if self in {PytestTestStatus.PASSED, PytestTestStatus.SKIPPED, PytestTestStatus.XFAIL}:
            return UnitTestStatus.PASSED
        return UnitTestStatus.FAILED


def parse_pytest_summary(content: str) -> dict[str, UnitTestStatus]:
    parts = re.split(
        pattern=r"=+\s*short test summary info\s*=+",
        string=content,
        flags=re.IGNORECASE,
        maxsplit=1,
    )
    if len(parts) < 2:
        return {}
    out: dict[str, UnitTestStatus] = {}
    for raw_line in parts[1].splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lower().startswith("failed"):
            chunks = line.split(" - ")
            if len(chunks) > 1:
                line = " - ".join(chunks[:-1])
        tokens = line.split(maxsplit=1)
        if len(tokens) < 2:
            continue
        status_token = tokens[0].strip().strip(":").upper()
        name_token = tokens[1].strip().split("::", maxsplit=1)[-1]
        if status_token not in PytestTestStatus.__members__:
            continue
        status = PytestTestStatus[status_token].to_test_status()
        if name_token:
            out[name_token] = status
    return out


def _normalize_result_map(values: Mapping[str, Any]) -> dict[str, UnitTestStatus]:
    out: dict[str, UnitTestStatus] = {}
    for test_name, status_value in values.items():
        normalized = str(status_value).strip().lower()
        out[str(test_name)] = (
            UnitTestStatus.PASSED if normalized == UnitTestStatus.PASSED.value else UnitTestStatus.FAILED
        )
    return out


@dataclass
class UnitTestResultScorer:
    metric_name: str = "accuracy"
    pass_rate_metric_name: str = "pass_rate"
    parser_name_field: str = "parser_name"
    default_parser_name: str = "pytest"
    parser_results_payload_key: str = "parser_results"
    parser_results_trace_event: str | None = None
    parser_results_trace_key: str = "parser_results"
    scorer_id: str = "unit_test_results"

    def _parser_name(self, context: ScoreContext) -> str:
        value = context.sample_metadata.get(self.parser_name_field, self.default_parser_name)
        return str(value).strip().lower() or self.default_parser_name

    def _extract_results(
        self,
        task_result: TaskResult,
        trace: Mapping[str, Any],
    ) -> dict[str, UnitTestStatus]:
        payload_results = task_result.payload.get(self.parser_results_payload_key)
        if isinstance(payload_results, Mapping):
            return _normalize_result_map(payload_results)

        if self.parser_results_trace_event:
            for event in trace.get("trace_events", []):
                if not isinstance(event, Mapping):
                    continue
                if str(event.get("event")) != self.parser_results_trace_event:
                    continue
                trace_results = event.get(self.parser_results_trace_key)
                if isinstance(trace_results, Mapping):
                    return _normalize_result_map(trace_results)

        output = task_result.final_output.get("content")
        if output is None:
            message = task_result.final_output.get("message")
            if isinstance(message, Mapping):
                output = message.get("content")
        return parse_pytest_summary(str(output or ""))

    def score(
        self,
        task_result: TaskResult,
        trace: Mapping[str, Any],
        context: ScoreContext,
    ) -> dict[str, Score]:
        parser_name = self._parser_name(context)
        if parser_name != "pytest":
            return {
                self.metric_name: Score(
                    value=0.0,
                    explanation=f"Unsupported parser '{parser_name}' in MVP scorer.",
                    metadata={"parser_name": parser_name, "supported": ["pytest"]},
                )
            }

        parsed = self._extract_results(task_result, trace)
        if not parsed:
            return {
                self.metric_name: Score(
                    value=0.0,
                    explanation="No parser results found in task_result payload/trace/output.",
                    metadata={"parser_name": parser_name, "parsed_tests": 0},
                )
            }

        total = len(parsed)
        passed = sum(1 for value in parsed.values() if value == UnitTestStatus.PASSED)
        pass_rate = passed / total if total else 0.0
        accuracy = 1.0 if passed == total else 0.0
        failed_tests = sorted([name for name, value in parsed.items() if value == UnitTestStatus.FAILED])
        return {
            self.metric_name: Score(
                value=accuracy,
                explanation=f"{passed}/{total} tests passed.",
                metadata={
                    "parser_name": parser_name,
                    "parsed_tests": total,
                    "passed_tests": passed,
                    "failed_tests": failed_tests,
                    "pass_rate": pass_rate,
                },
            ),
            self.pass_rate_metric_name: Score(value=pass_rate, explanation=f"{pass_rate:.3f}"),
        }


def unit_test_results(
    *,
    metric_name: str = "accuracy",
    pass_rate_metric_name: str = "pass_rate",
    parser_name_field: str = "parser_name",
    default_parser_name: str = "pytest",
    parser_results_payload_key: str = "parser_results",
    parser_results_trace_event: str | None = None,
    parser_results_trace_key: str = "parser_results",
) -> UnitTestResultScorer:
    return UnitTestResultScorer(
        metric_name=metric_name,
        pass_rate_metric_name=pass_rate_metric_name,
        parser_name_field=parser_name_field,
        default_parser_name=default_parser_name,
        parser_results_payload_key=parser_results_payload_key,
        parser_results_trace_event=parser_results_trace_event,
        parser_results_trace_key=parser_results_trace_key,
    )

