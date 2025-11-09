"""Unit tests for pytest-api-cov CLI module."""

from pathlib import Path
from unittest.mock import Mock, mock_open, patch

import pytest

from pytest_api_cov.cli import (
    generate_conftest_content,
    generate_pyproject_config,
    main,
)


class TestGenerateConftestContent:
    """Tests for generate_conftest_content function."""

    def test_fastapi_conftest(self):
        """Test generating conftest for FastAPI."""
        content = generate_conftest_content("FastAPI", "app.py", "app")

        assert "import pytest" in content
        assert "from fastapi.testclient import TestClient" in content
        assert "from app import app" in content
        assert "def client():" in content
        assert "The pytest-api-cov plugin can extract the app from your client fixture" in content
        assert "return TestClient(app)" in content

    def test_flask_conftest(self):
        """Test generating conftest for Flask."""
        content = generate_conftest_content("Flask", "main.py", "application")

        assert "import pytest" in content
        assert "from flask.testing import FlaskClient" in content
        assert "from main import application" in content
        assert "def client():" in content
        assert "The pytest-api-cov plugin can extract the app from your client fixture" in content
        assert "return FlaskClient(app)" in content

    def test_subdirectory_conftest(self):
        """Test generating conftest for app in subdirectory."""
        content = generate_conftest_content("FastAPI", "src/main.py", "app")

        assert "import pytest" in content
        assert "from src.main import app" in content
        assert "def client():" in content
        assert "return TestClient(app)" in content

    def test_nested_subdirectory_conftest(self):
        """Test generating conftest for app in nested subdirectory."""
        content = generate_conftest_content("Flask", "example/src/main.py", "app")

        assert "import pytest" in content
        assert "from example.src.main import app" in content
        assert "def client():" in content
        assert "return FlaskClient(app)" in content


class TestGeneratePyprojectConfig:
    """Tests for generate_pyproject_config function."""

    def test_pyproject_config_structure(self):
        """Test structure of generated pyproject config."""
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
    """Tests for main function."""

    def test_main_show_pyproject(self, monkeypatch):
        """Test main prints pyproject snippet for show-pyproject."""
        monkeypatch.setattr("sys.argv", ["pytest-api-cov", "show-pyproject"])
        with patch("builtins.print") as mock_print:
            result = main()
        assert result == 0
        mock_print.assert_called()

    def test_main_show_conftest(self, monkeypatch):
        """Test main prints conftest snippet for show-conftest."""
        monkeypatch.setattr("sys.argv", ["pytest-api-cov", "show-conftest", "FastAPI", "src.main", "app"])
        with patch("builtins.print") as mock_print:
            result = main()
        assert result == 0
        mock_print.assert_called()

    def test_main_no_command(self, monkeypatch):
        """Test main with no command (should show help)."""
        monkeypatch.setattr("sys.argv", ["pytest-api-cov"])
        result = main()

        assert result == 1

    def test_main_unknown_command(self):
        """Test main with unknown command."""
        with pytest.raises(SystemExit) as exc_info:
            monkeypatch = pytest.MonkeyPatch()
            try:
                monkeypatch.setenv("DUMMY", "1")  # noop to obtain monkeypatch object
                monkeypatch.setattr("sys.argv", ["pytest-api-cov", "unknown"])
                main()
            finally:
                monkeypatch.undo()

        assert exc_info.value.code == 2
