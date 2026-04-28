from snowl.core import Score
from snowl.scorer import workspace_diff


class WorkspaceSmokeScorer:
    scorer_id = "workspace_smoke"

    def score(self, task_result, trace, context):
        base = workspace_diff(metric_name="workspace_changed").score(task_result, trace, context)
        changed = base["workspace_changed"]
        return {
            "workspace_changed": changed,
            "accuracy": Score(changed.value, metadata=dict(changed.metadata)),
        }


scorer = WorkspaceSmokeScorer()

