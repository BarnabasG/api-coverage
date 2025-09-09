"""pytest flag configuration for API coverage."""

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import pytest


def add_pytest_api_cov_flags(parser: pytest.Parser) -> None:
    """Add API coverage flags to the parser."""
    parser.addoption(
        "--api-cov-report",
        action="store_true",
        default=False,
        help="Generate API coverage report.",
    )
    parser.addoption(
        "--api-cov-fail-under",
        action="store",
        type=float,
        default=None,
        help="Fail if API coverage is below this percentage.",
    )
    parser.addoption(
        "--api-cov-show-uncovered-endpoints",
        action="store_true",
        default=True,
        help="Show uncovered endpoints in the console report.",
    )
    parser.addoption(
        "--api-cov-show-covered-endpoints",
        action="store_true",
        default=False,
        help="Show covered endpoints in the console report.",
    )
    parser.addoption(
        "--api-cov-show-excluded-endpoints",
        action="store_true",
        default=False,
        help="Show excluded endpoints in the console report.",
    )
    parser.addoption(
        "--api-cov-exclusion-patterns",
        action="append",
        default=[],
        help="Patterns for endpoints to exclude from coverage.",
    )
    parser.addoption(
        "--api-cov-report-path",
        action="store",
        type=str,
        default=None,
        help="Path to save the API coverage report.",
    )
    parser.addoption(
        "--api-cov-force-sugar",
        action="store_true",
        default=False,
        help="Force use of API coverage sugar in console report.",
    )
    parser.addoption(
        "--api-cov-force-sugar-disabled",
        action="store_true",
        default=False,
        help="Disable use of API coverage sugar in console report.",
    )

    parser.addoption(
        "--api-cov-client-fixture-name",
        action="store",
        type=str,
        default=None,
        help="Name of existing test client fixture to wrap with coverage tracking",
    )
