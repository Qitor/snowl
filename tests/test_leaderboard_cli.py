"""Tests for snowl leaderboard CLI commands."""

import json
import pytest
import tempfile
from pathlib import Path

from snowl.cli import main


class TestLeaderboardPublish:
    def test_publish_missing_dir(self):
        exit_code = main(["leaderboard", "publish", "/nonexistent/path"])
        assert exit_code == 1

    def test_publish_no_summary(self, capsys):
        with tempfile.TemporaryDirectory() as tmpdir:
            exit_code = main(["leaderboard", "publish", tmpdir])
            assert exit_code == 1
            captured = capsys.readouterr()
            assert "no benchmark_summary" in captured.out.lower() or "error" in captured.out.lower()

    def test_publish_with_summary(self, capsys):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a benchmark_summary.json
            summary = {"model": "gpt-4o", "benchmark": "cybench", "success_rate": 0.85}
            summary_path = Path(tmpdir) / "benchmark_summary.json"
            summary_path.write_text(json.dumps(summary))

            exit_code = main(["leaderboard", "publish", tmpdir])
            assert exit_code == 0
            captured = capsys.readouterr()
            assert "published" in captured.out.lower()

            # Verify leaderboard.jsonl was created
            lb_path = Path(tmpdir).parent / "leaderboard.jsonl"
            assert lb_path.exists()


class TestLeaderboardList:
    def test_list_no_data(self, capsys):
        with tempfile.TemporaryDirectory() as tmpdir:
            import os
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                exit_code = main(["leaderboard", "list"])
                assert exit_code == 0
                captured = capsys.readouterr()
                assert "no leaderboard" in captured.out.lower() or "no leaderboard" in captured.out.lower()
            finally:
                os.chdir(old_cwd)


class TestLeaderboardCompare:
    def test_compare_missing_dir_a(self, capsys):
        with tempfile.TemporaryDirectory() as tmpdir_b:
            # Create summary for B
            summary_b = {"model": "gpt-4o", "success_rate": 0.9}
            Path(tmpdir_b, "benchmark_summary.json").write_text(json.dumps(summary_b))

            exit_code = main(["leaderboard", "compare", "/nonexistent", tmpdir_b])
            assert exit_code == 1

    def test_compare_with_summaries(self, capsys):
        with tempfile.TemporaryDirectory() as tmpdir_a, tempfile.TemporaryDirectory() as tmpdir_b:
            summary_a = {"model": "gpt-4o", "success_rate": 0.8, "accuracy": 0.75}
            summary_b = {"model": "claude-3", "success_rate": 0.9, "accuracy": 0.85}
            Path(tmpdir_a, "benchmark_summary.json").write_text(json.dumps(summary_a))
            Path(tmpdir_b, "benchmark_summary.json").write_text(json.dumps(summary_b))

            exit_code = main(["leaderboard", "compare", tmpdir_a, tmpdir_b])
            assert exit_code == 0
            captured = capsys.readouterr()
            assert "success_rate" in captured.out or "accuracy" in captured.out
