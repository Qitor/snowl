"""Tests for CLI registry commands."""

import pytest

from snowl.cli import main


class TestCLIRegistryList:
    def test_registry_list(self, capsys):
        exit_code = main(["registry", "list"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "benchmark" in captured.out.lower() or "cybench" in captured.out

    def test_registry_list_kind_benchmark(self, capsys):
        exit_code = main(["registry", "list", "--kind", "benchmark"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "[benchmark]" in captured.out

    def test_registry_list_kind_adapter(self, capsys):
        exit_code = main(["registry", "list", "--kind", "adapter"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "[adapter]" in captured.out


class TestCLIRegistryDoctor:
    def test_registry_doctor(self, capsys):
        exit_code = main(["registry", "doctor"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "OK" in captured.out or "passed" in captured.out.lower()


class TestCLIRegistryInfo:
    def test_registry_info_existing(self, capsys):
        exit_code = main(["registry", "info", "cybench"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "cybench" in captured.out

    def test_registry_info_missing(self, capsys):
        exit_code = main(["registry", "info", "no_such_thing"])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "error" in captured.out.lower() or "not found" in captured.out.lower()
