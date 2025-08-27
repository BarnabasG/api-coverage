"""Tests for pytest flag configuration."""

from unittest.mock import Mock, patch

from pytest_api_cov.pytest_flags import add_pytest_api_cov_flags


class TestPytestFlags:
    """Tests for pytest flag configuration."""

    @patch("builtins.print")
    def test_add_pytest_api_cov_flags(self, mock_print):
        """Test that all pytest flags are added correctly."""
        mock_parser = Mock()

        add_pytest_api_cov_flags(mock_parser)

        expected_calls = [
            ("--api-cov-report", "store_true", False, "Generate API coverage report."),
            ("--api-cov-fail-under", "store", None, "Fail if API coverage is below this percentage."),
            (
                "--api-cov-show-uncovered-endpoints",
                "store_true",
                True,
                "Show uncovered endpoints in the console report.",
            ),
            ("--api-cov-show-covered-endpoints", "store_true", False, "Show covered endpoints in the console report."),
            (
                "--api-cov-show-excluded-endpoints",
                "store_true",
                False,
                "Show excluded endpoints in the console report.",
            ),
            ("--api-cov-exclusion-patterns", "append", [], "Patterns for endpoints to exclude from coverage."),
            ("--api-cov-report-path", "store", None, "Path to save the API coverage report."),
            ("--api-cov-force-sugar", "store_true", False, "Force use of API coverage sugar in console report."),
            (
                "--api-cov-force-sugar-disabled",
                "store_true",
                False,
                "Disable use of API coverage sugar in console report.",
            ),
        ]

        assert mock_parser.addoption.call_count == len(expected_calls)

        for i, (option, action, default, help_text) in enumerate(expected_calls):
            call_args = mock_parser.addoption.call_args_list[i]
            assert call_args[1]["action"] == action
            assert call_args[1]["default"] == default
            assert call_args[1]["help"] == help_text

    def test_add_pytest_api_cov_flags_parser_interface(self):
        """Test that the parser interface is used correctly."""
        mock_parser = Mock()

        add_pytest_api_cov_flags(mock_parser)

        mock_parser.addoption.assert_called()

        first_call = mock_parser.addoption.call_args_list[0]
        assert first_call[0][0] == "--api-cov-report"
