# tests/test_config.py
import os
from unittest.mock import Mock, patch

import pytest
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
        """Verify reading a valid pyproject.toml."""
        pyproject_content = """
            [tool.pytest_api_cov]
            fail_under = 95.5
            show_covered_endpoints = true
            exclusion_patterns = ["/admin/*"]
        """
        (tmp_path / "pyproject.toml").write_text(pyproject_content)
        
        # Change to the tmp_path directory temporarily
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            config = read_toml_config()
            assert config["fail_under"] == 95.5
            assert config["show_covered_endpoints"] is True
            assert config["exclusion_patterns"] == ["/admin/*"]
        finally:
            os.chdir(original_cwd)

    def test_read_toml_config_file_not_found(self):
        """Ensure it returns an empty dict if pyproject.toml is missing."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            config = read_toml_config()
            assert config == {}

    def test_read_toml_config_missing_section(self, tmp_path):
        """Ensure it returns an empty dict if the [tool.pytest_api_cov] section is missing."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'")
        
        # Change to the tmp_path directory temporarily
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            config = read_toml_config()
            assert config == {}
        finally:
            os.chdir(original_cwd)

    def test_read_session_config(self):
        """Verify reading config from pytest's session object (CLI flags)."""
        mock_session_config = Mock()
        # Simulate providing some CLI flags and leaving others as default
        mock_session_config.getoption.side_effect = lambda name: {
            "--api-cov-fail-under": 80.0,
            "--api-cov-show-covered-endpoints": True,
            "--api-cov-report-path": "reports/cov.json",
        }.get(name)

        config = read_session_config(mock_session_config)
        assert config["fail_under"] == 80.0
        assert config["show_covered_endpoints"] is True
        assert config["report_path"] == "reports/cov.json"
        # Ensure unset options are not present
        assert "show_excluded_endpoints" not in config

    def test_read_session_config_with_false_values(self):
        """Test that False values are not included in config."""
        mock_session_config = Mock()
        mock_session_config.getoption.side_effect = lambda name: {
            "--api-cov-show-covered-endpoints": False,
            "--api-cov-exclusion-patterns": [],
        }.get(name)

        config = read_session_config(mock_session_config)
        assert "show_covered_endpoints" not in config
        assert "exclusion_patterns" not in config

    def test_read_session_config_with_none_values(self):
        """Test that None values are not included in config."""
        mock_session_config = Mock()
        mock_session_config.getoption.side_effect = lambda name: {
            "--api-cov-fail-under": None,
        }.get(name)

        config = read_session_config(mock_session_config)
        assert "fail_under" not in config

    # @pytest.mark.skip(reason="sys.stdout.encoding is readonly, skipping for now")
    # def test_supports_unicode(self):
    #     """Test the supports_unicode function."""
    #     # Test when stdout is not a tty
    #     with patch("sys.stdout.isatty", return_value=False):
    #         assert supports_unicode() is False

    #     # Test when stdout is a tty with UTF-8 encoding
    #     with patch("sys.stdout.isatty", return_value=True), \
    #          patch("sys.stdout.encoding", "utf-8", create=True):
    #         assert supports_unicode() is True

    #     # Test when stdout is a tty with UTF8 encoding
    #     with patch("sys.stdout.isatty", return_value=True), \
    #          patch("sys.stdout.encoding", "utf8", create=True):
    #         assert supports_unicode() is True

    #     # Test when stdout is a tty with non-UTF encoding
    #     with patch("sys.stdout.isatty", return_value=True), \
    #          patch("sys.stdout.encoding", "ascii", create=True):
    #         assert supports_unicode() is False

    #     # Test when stdout is None
    #     with patch("sys.stdout.isatty", return_value=True), \
    #          patch("sys.stdout", None):
    #         assert supports_unicode() is False


class TestConfigMerging:
    """Tests the merging logic of different config sources."""

    @patch("pytest_api_cov.config.read_session_config")
    @patch("pytest_api_cov.config.read_toml_config")
    def test_config_priority_cli_over_toml(self, mock_read_toml, mock_read_session):
        """Ensure CLI arguments override pyproject.toml settings."""
        mock_read_toml.return_value = {"fail_under": 90.0, "report_path": "toml.json"}
        mock_read_session.return_value = {"fail_under": 75.0}

        mock_session_config = Mock()
        final_config = get_pytest_api_cov_report_config(mock_session_config)

        assert final_config.fail_under == 75.0  # CLI wins
        assert final_config.report_path == "toml.json"  # From TOML
        assert final_config.show_uncovered_endpoints is True  # Default

    @patch("pytest_api_cov.config.read_session_config", return_value={})
    @patch("pytest_api_cov.config.read_toml_config")
    def test_pydantic_model_validation(self, mock_read_toml, mock_read_session):
        """Test that the Pydantic model correctly validates and sets defaults."""
        mock_read_toml.return_value = {"fail_under": 90.0}

        final_config = get_pytest_api_cov_report_config(Mock())

        assert final_config.fail_under == 90.0
        assert final_config.show_covered_endpoints is False  # Pydantic default
        assert final_config.exclusion_patterns == []  # Pydantic default

    @patch("pytest_api_cov.config.read_session_config", return_value={})
    @patch("pytest_api_cov.config.read_toml_config")
    @patch("pytest_api_cov.config.supports_unicode")
    def test_force_sugar_setting(self, mock_supports_unicode, mock_read_toml, mock_read_session):
        """Test force_sugar setting logic."""
        mock_supports_unicode.return_value = True
        mock_read_toml.return_value = {}

        # Test when force_sugar_disabled is set
        mock_read_session.return_value = {"force_sugar_disabled": True}
        config = get_pytest_api_cov_report_config(Mock())
        assert config.force_sugar is False

        # Test when force_sugar is not set (should use supports_unicode)
        mock_read_session.return_value = {}
        config = get_pytest_api_cov_report_config(Mock())
        assert config.force_sugar is True

        # Test when force_sugar is explicitly set
        mock_read_session.return_value = {"force_sugar": False}
        config = get_pytest_api_cov_report_config(Mock())
        assert config.force_sugar is False

    def test_pydantic_validation_error(self):
        """Ensure invalid types raise a validation error."""
        with pytest.raises(ValidationError):
            ApiCoverageReportConfig.model_validate({"fail_under": "not-a-float"})
