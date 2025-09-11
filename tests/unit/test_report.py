"""Tests for report generation."""

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
        discovered = ["/users", "/users/{user_id}", "/health", "/admin/dashboard", "/a/b/c", "/a/b/d/c"]
        called = {"/users", "/users/123", "/admin/dashboard"}
        excluded = ["*admin*", "/a/*/c"]

        covered, uncovered, excluded_out = categorise_endpoints(discovered, called, excluded)

        assert set(covered) == {"/users", "/users/{user_id}"}
        assert set(uncovered) == {"/health"}
        assert set(excluded_out) == {"/admin/dashboard", "/a/b/c", "/a/b/d/c"}

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

    def test_categorise_with_wildcard_exclusions(self):
        """Test categorization with wildcard exclusion patterns."""
        discovered = ["/public", "/admin/users", "/admin/settings", "/internal"]
        called = {"/public", "/admin/users"}
        excluded = ["/admin/*"]

        covered, uncovered, excluded_out = categorise_endpoints(discovered, called, excluded)
        assert set(covered) == {"/public"}
        assert set(uncovered) == {"/internal"}
        assert set(excluded_out) == {"/admin/users", "/admin/settings"}

    def test_categorise_with_literal_dot_patterns(self):
        """Test that dots in patterns are treated literally, not as regex wildcards."""
        discovered = ["/api/v1.0/users", "/api/v1x0/users", "/api/v2.0/users"]
        called = set()
        excluded = ["/api/v1.0/*"]

        covered, uncovered, excluded_out = categorise_endpoints(discovered, called, excluded)
        assert set(covered) == set()
        assert set(uncovered) == {"/api/v1x0/users", "/api/v2.0/users"}
        assert set(excluded_out) == {"/api/v1.0/users"}

    def test_categorise_with_negation_patterns(self):
        """Test categorization with negation patterns that override exclusions."""
        discovered = ["/users/alice", "/users/bob", "/users/charlie", "/admin/settings"]
        called = {"/users/alice", "/users/bob"}
        patterns = ["/users/*", "!/users/bob"]  # Exclude all users except bob

        covered, uncovered, excluded_out = categorise_endpoints(discovered, called, patterns)
        assert set(covered) == {"/users/bob"}  # bob is negated from exclusion
        assert set(uncovered) == {"/admin/settings"}
        assert set(excluded_out) == {"/users/alice", "/users/charlie"}  # alice and charlie are excluded

    def test_categorise_with_multiple_negation_patterns(self):
        """Test categorization with multiple negation patterns."""
        discovered = ["/api/v1/users", "/api/v1/admin", "/api/v1/public", "/api/v2/users", "/health"]
        called = {"/api/v1/users", "/api/v1/public"}
        patterns = ["/api/v1/*", "!/api/v1/users", "!/api/v1/public"]  # Exclude v1 except users and public

        covered, uncovered, excluded_out = categorise_endpoints(discovered, called, patterns)
        assert set(covered) == {"/api/v1/users", "/api/v1/public"}  # negated from exclusion
        assert set(uncovered) == {"/api/v2/users", "/health"}
        assert set(excluded_out) == {"/api/v1/admin"}  # only admin is excluded

    def test_categorise_with_negation_wildcard_patterns(self):
        """Test negation patterns with wildcards."""
        discovered = ["/admin/users/alice", "/admin/users/bob", "/admin/settings", "/public"]
        called = {"/admin/users/alice"}
        patterns = ["/admin/*", "!/admin/users/*"]  # Exclude all admin except admin/users/*

        covered, uncovered, excluded_out = categorise_endpoints(discovered, called, patterns)
        assert set(covered) == {"/admin/users/alice"}
        assert set(uncovered) == {"/admin/users/bob", "/public"}  # bob is uncovered but not excluded
        assert set(excluded_out) == {"/admin/settings"}  # settings is excluded

    def test_categorise_with_method_endpoint_negation(self):
        """Test negation patterns work with METHOD /path format."""
        discovered = ["GET /users/alice", "POST /users/alice", "GET /users/bob", "GET /admin"]
        called = {"GET /users/alice", "GET /users/bob"}
        patterns = ["/users/*", "!/users/bob"]  # Exclude all users except bob

        covered, uncovered, excluded_out = categorise_endpoints(discovered, called, patterns)
        assert set(covered) == {"GET /users/bob"}  # bob is negated from exclusion
        assert set(uncovered) == {"GET /admin"}
        assert set(excluded_out) == {"GET /users/alice", "POST /users/alice"}  # alice endpoints excluded

    def test_categorise_negation_without_matching_exclusion(self):
        """Test that negation patterns without matching exclusions don't affect anything."""
        discovered = ["/users/alice", "/users/bob", "/admin"]
        called = {"/users/alice"}
        patterns = ["!/users/charlie"]  # Negation for non-existent exclusion

        covered, uncovered, excluded_out = categorise_endpoints(discovered, called, patterns)
        assert set(covered) == {"/users/alice"}
        assert set(uncovered) == {"/users/bob", "/admin"}
        assert set(excluded_out) == set()  # Nothing excluded

    def test_categorise_complex_exclusion_negation_scenario(self):
        """Test complex scenario with multiple exclusions and negations."""
        discovered = [
            "/api/v1/users",
            "/api/v1/admin",
            "/api/v1/public",
            "/api/v2/users",
            "/api/v2/admin",
            "/health",
            "/metrics",
            "/docs",
        ]
        called = {"/api/v1/users", "/api/v1/public", "/health"}
        patterns = [
            "/api/v1/*",  # Exclude all v1 endpoints
            "/metrics",  # Exclude metrics
            "!/api/v1/users",  # But include v1/users
            "!/api/v1/public",  # But include v1/public
        ]

        covered, uncovered, excluded_out = categorise_endpoints(discovered, called, patterns)
        assert set(covered) == {"/api/v1/users", "/api/v1/public", "/health"}
        assert set(uncovered) == {"/api/v2/users", "/api/v2/admin", "/docs"}
        assert set(excluded_out) == {"/api/v1/admin", "/metrics"}


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
        error_print = next(c for c in mock_console.print.call_args_list if "No endpoints discovered" in c.args[0])
        assert "No endpoints discovered" in error_print.args[0]

    @pytest.mark.parametrize(
        "force_sugar,expected_symbols",
        [
            (True, ["❌", "✅", "🚫"]),  # Unicode symbols
            (False, ["[X]", "[.]", "[-]"]),  # ASCII symbols
        ],
    )
    @patch("pytest_api_cov.report.Console")
    def test_generate_report_sugar_symbols(self, mock_console_cls, force_sugar, expected_symbols):
        """Test report generation with different symbol configurations."""
        mock_console = mock_console_cls.return_value
        config = ApiCoverageReportConfig.model_validate(
            {
                "force_sugar": force_sugar,
                "show_uncovered_endpoints": True,
                "show_covered_endpoints": True,
                "show_excluded_endpoints": True,
            }
        )
        discovered = ["/a", "/b"]
        called = {"/a"}

        status = generate_pytest_api_cov_report(config, called, discovered)

        assert status == 0
        symbol_prints = [
            c for c in mock_console.print.call_args_list if any(symbol in c.args[0] for symbol in expected_symbols)
        ]
        assert len(symbol_prints) > 0


class TestPrintEndpoints:
    """Tests for the print_endpoints function."""

    @patch("pytest_api_cov.report.Console")
    def test_print_endpoints_with_endpoints(self, mock_console_cls):
        """Test print_endpoints when there are endpoints to print."""
        mock_console = mock_console_cls.return_value
        endpoints = ["/a", "/b"]

        print_endpoints(mock_console, "Test Label", endpoints, "✓", "green")

        assert mock_console.print.call_count == 3  # Label + 2 endpoints
        label_call = mock_console.print.call_args_list[0]
        assert "Test Label" in label_call.args[0]

    @patch("pytest_api_cov.report.Console")
    def test_print_endpoints_without_endpoints(self, mock_console_cls):
        """Test print_endpoints when there are no endpoints to print."""
        mock_console = mock_console_cls.return_value
        endpoints = []

        print_endpoints(mock_console, "Test Label", endpoints, "✓", "green")

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

        mock_open.assert_called_once()
        call_args = mock_open.call_args[0]
        assert call_args[0].name == "test_report.json"
        assert call_args[1] == "w"
        mock_json_dump.assert_called_once_with(report_data, mock_open.return_value.__enter__.return_value, indent=2)
