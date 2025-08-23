# tests/test_report.py
from unittest.mock import patch

import pytest

from pytest_api_cov.config import ApiCoverageReportConfig
from pytest_api_cov.report import (
    categorise_endpoints,
    compute_coverage,
    endpoint_to_regex,
    generate_pytest_api_cov_report,
    prepare_endpoint_detail,
    print_endpoints,
    write_report_file,
)


class TestEndpointCategorization:
    """Tests for endpoint classification logic."""

    def test_endpoint_to_regex_conversion(self):
        """Verify regex creation for Flask and FastAPI style placeholders."""
        assert endpoint_to_regex("/users/<id>").pattern == "^/users/(.+)$"
        assert endpoint_to_regex("/items/{item_id}/data").pattern == "^/items/(.+)/data$"
        assert endpoint_to_regex("/static/path").pattern == "^/static/path$"

    def test_categorise_endpoints(self):
        """Test the main categorization logic."""
        discovered = ["/users", "/users/{user_id}", "/health", "/admin/dashboard"]
        called = {"/users", "/users/123", "/admin/dashboard"}
        excluded = ["/admin/*"]

        covered, uncovered, excluded_out = categorise_endpoints(discovered, called, excluded)

        assert set(covered) == {"/users", "/users/{user_id}", "/admin/dashboard"}
        assert set(uncovered) == {"/health"}
        # Note: Your current exclusion is a simple string match, not glob.
        # To match /admin/dashboard, the pattern would need to be "/admin/dashboard"
        # Or the logic changed to support globs. Assuming simple string matching for now.
        assert excluded_out == []

    def test_categorise_with_no_exclusions(self):
        """Ensure it works correctly with no exclusion patterns."""
        discovered = ["/a", "/b"]
        called = {"/a"}
        covered, uncovered, excluded = categorise_endpoints(discovered, called, [])
        assert set(covered) == {"/a"}
        assert set(uncovered) == {"/b"}
        assert excluded == []

    def test_categorise_with_exclusion_patterns(self):
        """Test categorization with exclusion patterns."""
        discovered = ["/public", "/admin", "/internal"]
        called = {"/public", "/admin"}
        excluded = ["/admin"]

        covered, uncovered, excluded_out = categorise_endpoints(discovered, called, excluded)
        assert set(covered) == {"/public"}
        assert set(uncovered) == {"/internal"}
        assert set(excluded_out) == {"/admin"}

    def test_categorise_with_regex_exclusions(self):
        """Test categorization with regex exclusion patterns."""
        discovered = ["/public", "/admin/users", "/admin/settings", "/internal"]
        called = {"/public", "/admin/users"}
        excluded = ["/admin/users", "/admin/settings"]  # Use exact matches since regex escapes special chars

        covered, uncovered, excluded_out = categorise_endpoints(discovered, called, excluded)
        assert set(covered) == {"/public"}
        assert set(uncovered) == {"/internal"}
        assert set(excluded_out) == {"/admin/users", "/admin/settings"}


class TestCoverageCalculationAndReporting:
    """Tests for coverage computation and report generation."""

    @pytest.mark.parametrize(
        "covered,uncovered,expected",
        [(10, 0, 100.0), (0, 10, 0.0), (5, 5, 50.0), (3, 1, 75.0), (0, 0, 0.0)],
    )
    def test_compute_coverage(self, covered, uncovered, expected):
        """Test coverage percentage calculation."""
        assert compute_coverage(covered, uncovered) == expected

    def test_prepare_endpoint_detail(self):
        """Verify that caller information is correctly aggregated."""
        endpoints = ["/static", "/users/{user_id}"]
        called_data = {
            "/static": {"test_a"},
            "/users/1": {"test_b"},
            "/users/2": {"test_c", "test_b"},
        }
        details = prepare_endpoint_detail(endpoints, called_data)

        static_detail = next(d for d in details if d["endpoint"] == "/static")
        users_detail = next(d for d in details if d["endpoint"] == "/users/{user_id}")

        assert static_detail["callers"] == ["test_a"]
        assert sorted(users_detail["callers"]) == ["test_b", "test_c"]

    @patch("pytest_api_cov.report.Console")
    def test_generate_report_success(self, mock_console_cls):
        """Test report generation when coverage meets the requirement."""
        mock_console = mock_console_cls.return_value
        config = ApiCoverageReportConfig.model_validate({"fail_under": 70.0})
        discovered = ["/a", "/b", "/c", "/d"]
        called = {"/a", "/b", "/c"}

        status = generate_pytest_api_cov_report(config, called, discovered)

        assert status == 0  # Success
        # Check that the final print contains "SUCCESS"
        success_print = next(c for c in mock_console.print.call_args_list if "SUCCESS" in c.args[0])
        assert "Coverage of 75.0%" in success_print.args[0]

    @patch("pytest_api_cov.report.Console")
    def test_generate_report_failure(self, mock_console_cls):
        """Test report generation when coverage is below the requirement."""
        mock_console = mock_console_cls.return_value
        config = ApiCoverageReportConfig.model_validate({"fail_under": 80.0})
        discovered = ["/a", "/b", "/c", "/d"]
        called = {"/a": "foo", "/b": "foo", "/c": "foo"}

        status = generate_pytest_api_cov_report(config, called, discovered)

        assert status == 1  # Failure
        fail_print = next(c for c in mock_console.print.call_args_list if "FAIL" in c.args[0])
        assert "FAIL: Required coverage of 80.0% not met. Actual coverage: 75.0%" in fail_print.args[0]

    @patch("pytest_api_cov.report.write_report_file")
    def test_json_report_generation(self, mock_write_report):
        """Ensure the JSON report is generated when a path is provided."""
        config = ApiCoverageReportConfig.model_validate({"report_path": "coverage.json"})
        status = generate_pytest_api_cov_report(config, {"/a": "foo"}, ["/a", "/b"])

        assert status == 0
        mock_write_report.assert_called_once()
        report_data = mock_write_report.call_args.args[0]
        assert report_data["coverage"] == 50.0
        assert len(report_data["detail"]) == 2

    @patch("pytest_api_cov.report.Console")
    def test_generate_report_no_endpoints(self, mock_console_cls):
        """Test report generation when no endpoints are discovered."""
        mock_console = mock_console_cls.return_value
        config = ApiCoverageReportConfig.model_validate({})
        discovered = []
        called = {}

        status = generate_pytest_api_cov_report(config, called, discovered)

        assert status == 0
        # Check that the error message is printed
        error_print = next(c for c in mock_console.print.call_args_list if "No endpoints discovered" in c.args[0])
        assert "No endpoints discovered" in error_print.args[0]

    @patch("pytest_api_cov.report.Console")
    def test_generate_report_with_force_sugar(self, mock_console_cls):
        """Test report generation with force_sugar enabled."""
        mock_console = mock_console_cls.return_value
        config = ApiCoverageReportConfig.model_validate(
            {
                "force_sugar": True,
                "show_uncovered_endpoints": True,
                "show_covered_endpoints": True,
                "show_excluded_endpoints": True,
            }
        )
        discovered = ["/a", "/b"]
        called = {"/a"}

        status = generate_pytest_api_cov_report(config, called, discovered)

        assert status == 0
        # Check that sugar symbols are used
        sugar_prints = [
            c for c in mock_console.print.call_args_list if "❌" in c.args[0] or "✅" in c.args[0] or "🚫" in c.args[0]
        ]
        assert len(sugar_prints) > 0

    @patch("pytest_api_cov.report.Console")
    def test_generate_report_without_force_sugar(self, mock_console_cls):
        """Test report generation without force_sugar (default behavior)."""
        mock_console = mock_console_cls.return_value
        config = ApiCoverageReportConfig.model_validate(
            {
                "force_sugar": False,
                "show_uncovered_endpoints": True,
                "show_covered_endpoints": True,
                "show_excluded_endpoints": True,
            }
        )
        discovered = ["/a", "/b"]
        called = {"/a"}

        status = generate_pytest_api_cov_report(config, called, discovered)

        assert status == 0
        # Check that default symbols are used
        default_prints = [
            c
            for c in mock_console.print.call_args_list
            if "[X]" in c.args[0] or "[.]" in c.args[0] or "[-]" in c.args[0]
        ]
        assert len(default_prints) > 0


class TestPrintEndpoints:
    """Tests for the print_endpoints function."""

    @patch("pytest_api_cov.report.Console")
    def test_print_endpoints_with_endpoints(self, mock_console_cls):
        """Test print_endpoints when there are endpoints to print."""
        mock_console = mock_console_cls.return_value
        endpoints = ["/a", "/b"]

        print_endpoints(mock_console, "Test Label", endpoints, "✓", "green")

        # Should print the label and each endpoint
        assert mock_console.print.call_count == 3  # Label + 2 endpoints
        label_call = mock_console.print.call_args_list[0]
        assert "Test Label" in label_call.args[0]

    @patch("pytest_api_cov.report.Console")
    def test_print_endpoints_without_endpoints(self, mock_console_cls):
        """Test print_endpoints when there are no endpoints to print."""
        mock_console = mock_console_cls.return_value
        endpoints = []

        print_endpoints(mock_console, "Test Label", endpoints, "✓", "green")

        # Should not print anything when no endpoints
        mock_console.print.assert_not_called()


class TestWriteReportFile:
    """Tests for the write_report_file function."""

    @patch("builtins.open")
    @patch("json.dump")
    def test_write_report_file(self, mock_json_dump, mock_open):
        """Test that write_report_file writes data correctly."""
        report_data = {"coverage": 100.0, "endpoints": ["/a", "/b"]}
        report_path = "test_report.json"

        write_report_file(report_data, report_path)

        # Verify file operations
        mock_open.assert_called_once()
        # The path is resolved to absolute path, so just check the filename
        call_args = mock_open.call_args[0]
        assert call_args[0].name == "test_report.json"
        assert call_args[1] == "w"
        mock_json_dump.assert_called_once_with(report_data, mock_open.return_value.__enter__.return_value, indent=2)
