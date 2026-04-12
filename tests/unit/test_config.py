"""Tests for configuration module."""

import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import tomli
from pydantic import ValidationError

from pytest_api_cov.config import (
    ApiCoverageReportConfig,
    get_pytest_api_cov_report_config,
    read_session_config,
    read_toml_config,
    supports_unicode,
)


class TestConfigLoading:
    """Tests for loading configuration from different sources."""

    def test_read_toml_config_success(self, tmp_path):
        """Read a valid pyproject.toml."""
        pyproject_content = """
            [tool.pytest_api_cov]
            fail_under = 95.5
            show_covered_endpoints = true
            exclusion_patterns = ["/admin/*"]
        """
        (tmp_path / "pyproject.toml").write_text(pyproject_content)

        original_cwd = Path.cwd()
        os.chdir(tmp_path)
        try:
            config = read_toml_config()
            assert config["fail_under"] == 95.5
            assert config["show_covered_endpoints"] is True
            assert config["exclusion_patterns"] == ["/admin/*"]
        finally:
            os.chdir(original_cwd)

    def test_read_toml_config_file_not_found(self):
        """Return empty dict when pyproject.toml is missing."""
        with patch("pathlib.Path.open", side_effect=FileNotFoundError):
            config = read_toml_config()
            assert config == {}

    def test_read_toml_config_toml_decode_error(self):
        """Return empty dict on TOML syntax errors."""
        with patch("pathlib.Path.open", side_effect=tomli.TOMLDecodeError("Invalid TOML", "", 0)):
            config = read_toml_config()
            assert config == {}

    def test_read_toml_config_missing_section(self, tmp_path):
        """Return empty dict when [tool.pytest_api_cov] section is absent."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'")

        original_cwd = Path.cwd()
        os.chdir(tmp_path)
        try:
            config = read_toml_config()
            assert config == {}
        finally:
            os.chdir(original_cwd)

    def test_read_session_config(self):
        """Read config from pytest CLI flags."""
        mock_session_config = Mock()
        mock_session_config.getoption.side_effect = lambda name: {
            "--api-cov-fail-under": 80.0,
            "--api-cov-show-covered-endpoints": True,
            "--api-cov-report-path": "reports/cov.json",
        }.get(name)

        config = read_session_config(mock_session_config)
        assert config["fail_under"] == 80.0
        assert config["show_covered_endpoints"] is True
        assert config["report_path"] == "reports/cov.json"
        assert "show_excluded_endpoints" not in config

    def test_read_session_config_with_false_values(self):
        """False values are not included in config."""
        mock_session_config = Mock()
        mock_session_config.getoption.side_effect = lambda name: {
            "--api-cov-show-covered-endpoints": False,
            "--api-cov-exclusion-patterns": [],
        }.get(name)

        config = read_session_config(mock_session_config)
        assert "show_covered_endpoints" not in config
        assert "exclusion_patterns" not in config

    def test_read_session_config_with_none_values(self):
        """None values are not included in config."""
        mock_session_config = Mock()
        mock_session_config.getoption.side_effect = lambda name: {
            "--api-cov-fail-under": None,
        }.get(name)

        config = read_session_config(mock_session_config)
        assert "fail_under" not in config

    @pytest.mark.parametrize(
        ("is_tty", "encoding", "expected"),
        [
            (False, "utf-8", False),
            (True, "utf-8", True),
            (True, "UTF8", True),
            (True, "ascii", False),
        ],
    )
    def test_supports_unicode(self, is_tty, encoding, expected):
        """Check unicode support detection."""
        mock_stdout = Mock()
        mock_stdout.isatty.return_value = is_tty
        mock_stdout.encoding = encoding

        with patch("sys.stdout", mock_stdout):
            assert supports_unicode() == expected


class TestConfigMerging:
    """Tests for config merging logic."""

    @patch("pytest_api_cov.config.read_session_config")
    @patch("pytest_api_cov.config.read_toml_config")
    def test_config_priority_cli_over_toml(self, mock_read_toml, mock_read_session):
        """CLI arguments override pyproject.toml settings."""
        mock_read_toml.return_value = {"fail_under": 90.0, "report_path": "toml.json"}
        mock_read_session.return_value = {"fail_under": 75.0}

        mock_session_config = Mock()
        final_config = get_pytest_api_cov_report_config(mock_session_config)

        assert final_config.fail_under == 75.0
        assert final_config.report_path == "toml.json"
        assert final_config.show_uncovered_endpoints is True

    @patch("pytest_api_cov.config.read_session_config", return_value={})
    @patch("pytest_api_cov.config.read_toml_config")
    def test_pydantic_model_validation(self, mock_read_toml, mock_read_session):
        """Pydantic model validates and sets defaults correctly."""
        mock_read_toml.return_value = {"fail_under": 90.0}

        final_config = get_pytest_api_cov_report_config(Mock())

        assert final_config.fail_under == 90.0
        assert final_config.show_covered_endpoints is False
        assert final_config.exclusion_patterns == []
        mock_read_session.assert_called_once()

    @patch("pytest_api_cov.config.read_session_config", return_value={})
    @patch("pytest_api_cov.config.read_toml_config")
    @patch("pytest_api_cov.config.supports_unicode")
    def test_force_sugar_setting(self, mock_supports_unicode, mock_read_toml, mock_read_session):
        """force_sugar respects disabled flag and unicode support."""
        mock_supports_unicode.return_value = True
        mock_read_toml.return_value = {}

        mock_read_session.return_value = {"force_sugar_disabled": True}
        config = get_pytest_api_cov_report_config(Mock())
        assert config.force_sugar is False

        mock_read_session.return_value = {}
        config = get_pytest_api_cov_report_config(Mock())
        assert config.force_sugar is True

        mock_read_session.return_value = {"force_sugar": False}
        config = get_pytest_api_cov_report_config(Mock())
        assert config.force_sugar is False

    def test_pydantic_validation_error(self):
        """Invalid types raise ValidationError."""
        with pytest.raises(ValidationError):
            ApiCoverageReportConfig.model_validate({"fail_under": "not-a-float"})

    def test_read_session_config_empty_options(self):
        """No options set returns empty dict."""
        mock_session_config = Mock()
        mock_session_config.getoption.return_value = None

        config = read_session_config(mock_session_config)
        assert config == {}

    def test_read_session_config_with_empty_list(self):
        """Empty list value is treated as unset."""
        mock_session_config = Mock()
        mock_session_config.getoption.side_effect = lambda name: {
            "--api-cov-exclusion-patterns": [],
        }.get(name)

        config = read_session_config(mock_session_config)
        assert "exclusion_patterns" not in config

    def test_read_session_config_with_false_boolean(self):
        """False boolean value is treated as unset."""
        mock_session_config = Mock()
        mock_session_config.getoption.side_effect = lambda name: {
            "--api-cov-show-covered-endpoints": False,
        }.get(name)

        config = read_session_config(mock_session_config)
        assert "show_covered_endpoints" not in config

    def test_read_session_config_with_none_value(self):
        """None value is treated as unset."""
        mock_session_config = Mock()
        mock_session_config.getoption.side_effect = lambda name: {
            "--api-cov-fail-under": None,
        }.get(name)

        config = read_session_config(mock_session_config)
        assert "fail_under" not in config

    def test_read_session_config_with_openapi_spec(self):
        """openapi_spec is read from CLI flags."""
        mock_session_config = Mock()
        mock_session_config.getoption.side_effect = lambda name: {
            "--api-cov-openapi-spec": "openapi.json",
        }.get(name)

        config = read_session_config(mock_session_config)
        assert config["openapi_spec"] == "openapi.json"

    def test_read_toml_config_with_openapi_spec(self, tmp_path):
        """openapi_spec is read from pyproject.toml."""
        pyproject_content = """
            [tool.pytest_api_cov]
            openapi_spec = "openapi.yaml"
        """
        (tmp_path / "pyproject.toml").write_text(pyproject_content)

        original_cwd = Path.cwd()
        os.chdir(tmp_path)
        try:
            config = read_toml_config()
            assert config["openapi_spec"] == "openapi.yaml"
        finally:
            os.chdir(original_cwd)
