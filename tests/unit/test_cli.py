"""Unit tests for pytest-api-cov CLI module."""

from unittest.mock import patch

import pytest

from pytest_api_cov.cli import (
    generate_conftest_content,
    generate_pyproject_config,
    main,
)


class TestGenerateConftestContent:
    """Tests for generate_conftest_content."""

    def test_fastapi_conftest(self):
        """Generate conftest for FastAPI."""
        content = generate_conftest_content("FastAPI", "app.py", "app")

        assert "import pytest" in content
        assert "from fastapi.testclient import TestClient" in content
        assert "from app import app" in content
        assert "def client():" in content
        assert "return TestClient(app)" in content

    def test_flask_conftest(self):
        """Generate conftest for Flask."""
        content = generate_conftest_content("Flask", "main.py", "application")

        assert "import pytest" in content
        assert "from flask.testing import FlaskClient" in content
        assert "from main import application" in content
        assert "def client():" in content
        assert "return FlaskClient(app)" in content

    def test_subdirectory_conftest(self):
        """Generate conftest for app in subdirectory."""
        content = generate_conftest_content("FastAPI", "src/main.py", "app")

        assert "import pytest" in content
        assert "from src.main import app" in content
        assert "def client():" in content
        assert "return TestClient(app)" in content

    def test_nested_subdirectory_conftest(self):
        """Generate conftest for app in nested subdirectory."""
        content = generate_conftest_content("Flask", "example/src/main.py", "app")

        assert "import pytest" in content
        assert "from example.src.main import app" in content
        assert "def client():" in content
        assert "return FlaskClient(app)" in content


class TestGeneratePyprojectConfig:
    """Tests for generate_pyproject_config."""

    def test_pyproject_config_structure(self):
        """Verify generated pyproject config contains expected sections."""
        config = generate_pyproject_config()

        assert "[tool.pytest_api_cov]" in config
        assert "show_uncovered_endpoints = true" in config
        assert "show_covered_endpoints = false" in config
        assert "show_excluded_endpoints = false" in config
        assert "# fail_under = 80.0" in config
        assert "# exclusion_patterns" in config
        assert "# report_path" in config
        assert "# force_sugar" in config


class TestMain:
    """Tests for main CLI entry point."""

    def test_main_show_pyproject(self, monkeypatch):
        """show-pyproject prints config snippet."""
        monkeypatch.setattr("sys.argv", ["pytest-api-cov", "show-pyproject"])
        with patch("builtins.print") as mock_print:
            result = main()
        assert result == 0
        mock_print.assert_called()

    def test_main_show_conftest(self, monkeypatch):
        """show-conftest prints conftest snippet."""
        monkeypatch.setattr("sys.argv", ["pytest-api-cov", "show-conftest", "FastAPI", "src.main", "app"])
        with patch("builtins.print") as mock_print:
            result = main()
        assert result == 0
        mock_print.assert_called()

    def test_main_no_command(self, monkeypatch):
        """No command returns exit code 1."""
        monkeypatch.setattr("sys.argv", ["pytest-api-cov"])
        result = main()

        assert result == 1

    def test_main_unknown_command(self):
        """Unknown command exits with code 2."""
        with pytest.raises(SystemExit) as exc_info:
            monkeypatch = pytest.MonkeyPatch()
            try:
                monkeypatch.setenv("DUMMY", "1")
                monkeypatch.setattr("sys.argv", ["pytest-api-cov", "unknown"])
                main()
            finally:
                monkeypatch.undo()

        assert exc_info.value.code == 2
