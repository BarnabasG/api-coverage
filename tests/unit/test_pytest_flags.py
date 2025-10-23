"""Tests for pytest flag configuration."""

from unittest.mock import Mock

from pytest_api_cov.pytest_flags import add_pytest_api_cov_flags


class TestPytestFlags:
    """Tests for pytest flag configuration."""

    def test_add_pytest_api_cov_flags_parser_interface(self):
        """Test that the parser interface is used correctly."""
        mock_parser = Mock()

        add_pytest_api_cov_flags(mock_parser)

        mock_parser.addoption.assert_called()

        first_call = mock_parser.addoption.call_args_list[0]
        assert first_call[0][0] == "--api-cov-report"
