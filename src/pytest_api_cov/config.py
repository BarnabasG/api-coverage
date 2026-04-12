"""Configuration handling for the API coverage report."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import tomli
from pydantic import BaseModel, ConfigDict, Field


class ApiCoverageReportConfig(BaseModel):
    """Configuration model for API coverage reporting."""

    model_config = ConfigDict(populate_by_name=True)

    fail_under: float | None = Field(None, alias="api-cov-fail-under")
    show_uncovered_endpoints: bool = Field(default=True, alias="api-cov-show-uncovered-endpoints")
    show_covered_endpoints: bool = Field(default=False, alias="api-cov-show-covered-endpoints")
    show_excluded_endpoints: bool = Field(default=False, alias="api-cov-show-excluded-endpoints")
    exclusion_patterns: list[str] = Field(default=[], alias="api-cov-exclusion-patterns")
    report_path: str | None = Field(None, alias="api-cov-report-path")
    force_sugar: bool = Field(default=False, alias="api-cov-force-sugar")
    force_sugar_disabled: bool = Field(default=False, alias="api-cov-force-sugar-disabled")
    client_fixture_names: list[str] = Field(
        ["client", "test_client", "api_client", "app_client"], alias="api-cov-client-fixture-names"
    )
    group_methods_by_endpoint: bool = Field(default=False, alias="api-cov-group-methods-by-endpoint")
    openapi_spec: str | None = Field(None, alias="api-cov-openapi-spec")


def read_toml_config() -> dict[str, Any]:
    """Read the [tool.pytest_api_cov] section from pyproject.toml."""
    try:
        with Path("pyproject.toml").open("rb") as f:
            toml_config = tomli.load(f)
            return toml_config.get("tool", {}).get("pytest_api_cov", {})  # type: ignore[no-any-return]
    except (FileNotFoundError, tomli.TOMLDecodeError):
        return {}


_CLI_OPTIONS = {
    "api-cov-fail-under": "fail_under",
    "api-cov-show-uncovered-endpoints": "show_uncovered_endpoints",
    "api-cov-show-covered-endpoints": "show_covered_endpoints",
    "api-cov-show-excluded-endpoints": "show_excluded_endpoints",
    "api-cov-exclusion-patterns": "exclusion_patterns",
    "api-cov-report-path": "report_path",
    "api-cov-force-sugar": "force_sugar",
    "api-cov-force-sugar-disabled": "force_sugar_disabled",
    "api-cov-client-fixture-names": "client_fixture_names",
    "api-cov-group-methods-by-endpoint": "group_methods_by_endpoint",
    "api-cov-openapi-spec": "openapi_spec",
}

_UNSET = (None, [], False)


def read_session_config(session_config: Any) -> dict[str, Any]:
    """Read configuration from pytest session config (command-line flags)."""
    config: dict[str, Any] = {}
    for opt, key in _CLI_OPTIONS.items():
        value = session_config.getoption(f"--{opt}")
        if value not in _UNSET:
            config[key] = value

    if session_config.getoption("--api-cov-hide-uncovered-endpoints"):
        config["show_uncovered_endpoints"] = False

    return config


def supports_unicode() -> bool:
    """Check if the terminal supports Unicode output."""
    if not sys.stdout.isatty():
        return False
    return sys.stdout.encoding.lower() in ("utf-8", "utf8")


def get_pytest_api_cov_report_config(session_config: Any) -> ApiCoverageReportConfig:
    """Build final config by merging sources. Priority: CLI > pyproject.toml > defaults."""
    toml_config = read_toml_config()
    cli_config = read_session_config(session_config)

    final_config = {**toml_config, **cli_config}

    if final_config.get("force_sugar_disabled"):
        final_config["force_sugar"] = False
    elif "force_sugar" not in final_config:
        final_config["force_sugar"] = supports_unicode()

    return ApiCoverageReportConfig.model_validate(final_config)
