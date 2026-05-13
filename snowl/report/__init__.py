"""Report generation package — Jinja2-templated HTML, JSON, and Markdown reports.

Framework role:
- Provides ``render_report`` for generating evaluation reports from aggregate data.
- Replaces the inline f-string HTML generation in ``artifacts.py``.

Runtime/usage wiring:
- Called from ``RunArtifactStore._html_report()`` and ``snowl report`` CLI command.
"""

from snowl.report.html import render_report

__all__ = ["render_report"]
