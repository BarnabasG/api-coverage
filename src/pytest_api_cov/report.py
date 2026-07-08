"""API coverage report generation."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from re import Pattern
from typing import TYPE_CHECKING, Any

from rich.console import Console

if TYPE_CHECKING:
    from .config import ApiCoverageReportConfig


@lru_cache(maxsize=512)
def endpoint_to_regex(endpoint: str) -> Pattern[str]:
    """Create a regex pattern from an endpoint by replacing dynamic segments.

    Plain parameters match a single path segment so a call to a nested path
    cannot mark a parent route covered; path-converter parameters (Flask
    ``<path:x>``, Starlette ``{x:path}``) still match across segments.
    """
    segment_placeholder = "___SEGMENT___"
    path_placeholder = "___PATH___"

    def _placeholder(match: re.Match[str]) -> str:
        inner = match.group(0)[1:-1]
        if inner.startswith("path:") or inner.endswith(":path"):
            return path_placeholder
        return segment_placeholder

    temp_endpoint = re.escape(re.sub(r"<[^>]+>|\{[^}]+\}", _placeholder, endpoint))
    pattern = temp_endpoint.replace(segment_placeholder, "([^/]+)").replace(path_placeholder, "(.+)")
    return re.compile("^" + pattern + "$")


def contains_escape_characters(endpoint: str) -> bool:
    """Check whether an endpoint contains dynamic path segments."""
    return ("<" in endpoint and ">" in endpoint) or ("{" in endpoint and "}" in endpoint)


def _compile_exclusion_pattern(pat: str) -> tuple[frozenset[str] | None, Pattern[str]]:
    """Compile a single exclusion pattern into a (methods, regex) pair."""
    path_pattern = pat.strip()
    methods: frozenset[str] | None = None
    m = re.match(r"^([A-Za-z,]+)\s+(.+)$", pat)
    if m:
        methods = frozenset(mname.strip().upper() for mname in m.group(1).split(",") if mname.strip())
        path_pattern = m.group(2)
    regex = re.compile("^" + re.escape(path_pattern).replace(r"\*", ".*") + "$")
    return methods, regex


_CompiledPatterns = tuple[tuple[frozenset[str] | None, Pattern[str]], ...]


@lru_cache(maxsize=128)
def _compile_exclusion_patterns(
    patterns: tuple[str, ...],
) -> tuple[_CompiledPatterns | None, _CompiledPatterns | None]:
    """Compile and cache exclusion/negation patterns.

    Accepts a tuple (hashable) so the result can be cached across calls.
    """
    exclusion_only = [p for p in patterns if not p.startswith("!")]
    negation_only = [p[1:] for p in patterns if p.startswith("!")]

    compiled_exclusions = tuple(_compile_exclusion_pattern(p) for p in exclusion_only) if exclusion_only else None
    compiled_negations = tuple(_compile_exclusion_pattern(p) for p in negation_only) if negation_only else None
    return compiled_exclusions, compiled_negations


def categorise_endpoints(
    endpoints: list[str],
    called_data: dict[str, set[str]],
    exclusion_patterns: list[str],
) -> tuple[list[str], list[str], list[str]]:
    """Categorise endpoints into covered, uncovered, and excluded.

    Exclusion patterns support wildcard matching with negation and optional
    HTTP method prefixes. Pattern order matters: exclusions first, then
    negations override them.
    """
    covered: list[str] = []
    uncovered: list[str] = []
    excluded: list[str] = []

    if not exclusion_patterns:
        compiled_exclusions = None
        compiled_negations = None
    else:
        compiled_exclusions, compiled_negations = _compile_exclusion_patterns(tuple(exclusion_patterns))

    for endpoint in endpoints:
        is_excluded = False
        endpoint_method = None
        path_only = endpoint
        if " " in endpoint:
            endpoint_method, path_only = endpoint.split(" ", 1)
            endpoint_method = endpoint_method.upper()

        if compiled_exclusions:
            for methods_set, regex in compiled_exclusions:
                if methods_set:
                    if not endpoint_method or endpoint_method not in methods_set:
                        continue
                    if regex.match(path_only) or regex.match(endpoint):
                        is_excluded = True
                        break
                elif regex.match(path_only) or regex.match(endpoint):
                    is_excluded = True
                    break

        if is_excluded and compiled_negations:
            for methods_set, regex in compiled_negations:
                if methods_set:
                    if not endpoint_method or endpoint_method not in methods_set:
                        continue
                    if regex.match(path_only) or regex.match(endpoint):
                        is_excluded = False
                        break
                elif regex.match(path_only) or regex.match(endpoint):
                    is_excluded = False
                    break

        if is_excluded:
            excluded.append(endpoint)
            continue
        if contains_escape_characters(endpoint):
            pattern = endpoint_to_regex(endpoint)
            is_covered = any(pattern.match(ep) for ep in called_data)
        else:
            is_covered = endpoint in called_data
        covered.append(endpoint) if is_covered else uncovered.append(endpoint)
    return covered, uncovered, excluded


def group_endpoints_by_path(
    endpoints: list[str],
    called_data: dict[str, set[str]],
) -> tuple[list[str], dict[str, set[str]]]:
    """Collapse 'METHOD /path' keys to '/path', merging caller sets across methods."""
    grouped_endpoints: list[str] = []
    seen: set[str] = set()
    for endpoint in endpoints:
        path = endpoint.split(" ", 1)[1] if " " in endpoint else endpoint
        if path not in seen:
            seen.add(path)
            grouped_endpoints.append(path)

    grouped_calls: dict[str, set[str]] = {}
    for key, callers in called_data.items():
        path = key.split(" ", 1)[1] if " " in key else key
        grouped_calls.setdefault(path, set()).update(callers)

    return grouped_endpoints, grouped_calls


def print_endpoints(
    console: Console,
    label: str,
    endpoints: list[str],
    symbol: str,
    style: str,
) -> None:
    """Print a list of endpoints to the console."""
    if endpoints:
        console.print(f"[{style}]{label}[/]:")
        for endpoint in endpoints:
            if " " in endpoint:
                method, path = endpoint.split(" ", 1)
                formatted_endpoint = f"{method:<6} {path}"
            else:
                formatted_endpoint = endpoint
            console.print(f"  {symbol}\t[{style}]{formatted_endpoint}[/]")


def compute_coverage(covered_count: int, uncovered_count: int) -> float:
    """Compute API coverage percentage."""
    total = covered_count + uncovered_count
    return round(100 * covered_count / total, 2) if total > 0 else 0.0


def prepare_endpoint_detail(endpoints: list[str], called_data: dict[str, set[str]]) -> list[dict[str, Any]]:
    """Map each endpoint to its callers for JSON report output."""
    details = []
    for endpoint in endpoints:
        if contains_escape_characters(endpoint):
            pattern = endpoint_to_regex(endpoint)
            callers: set[str] = set()
            for call, call_set in called_data.items():
                if pattern.match(call):
                    callers.update(call_set)
        else:
            callers = called_data.get(endpoint, set())
        details.append({"endpoint": endpoint, "callers": sorted(callers)})
    return sorted(details, key=lambda x: len(x["callers"]))


def write_report_file(report_data: dict[str, Any], report_path: str) -> None:
    """Write the report data to a JSON file."""
    path = Path(report_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(report_data, f, indent=2)


def generate_pytest_api_cov_report(
    api_cov_config: ApiCoverageReportConfig,
    called_data: dict[str, set[str]],
    discovered_endpoints: list[str],
) -> int:
    """Generate and print the API coverage report, returning an exit status."""
    console = Console()

    if not discovered_endpoints:
        if api_cov_config.fail_under is not None:
            console.print(
                f"\n[bold red]FAIL: No endpoints discovered but --api-cov-fail-under={api_cov_config.fail_under} "
                "is set. Check your app/client fixtures or OpenAPI spec.[/bold red]"
            )
            return 1
        console.print("\n[bold red]No endpoints discovered. Please check your test setup.[/bold red]")
        return 0

    separator = "=" * 20
    console.print(f"\n\n[bold blue]{separator} API Coverage Report {separator}[/bold blue]")

    if api_cov_config.group_methods_by_endpoint:
        discovered_endpoints, called_data = group_endpoints_by_path(discovered_endpoints, called_data)

    covered, uncovered, excluded = categorise_endpoints(
        discovered_endpoints,
        called_data,
        api_cov_config.exclusion_patterns,
    )

    if api_cov_config.show_uncovered_endpoints:
        print_endpoints(
            console,
            "Uncovered Endpoints",
            uncovered,
            "❌" if api_cov_config.force_sugar else "[X]",
            "red",
        )

    if api_cov_config.show_covered_endpoints:
        print_endpoints(
            console,
            "Covered Endpoints",
            covered,
            "✅" if api_cov_config.force_sugar else "[.]",
            "green",
        )

    if api_cov_config.show_excluded_endpoints:
        print_endpoints(
            console,
            label="Excluded Endpoints",
            endpoints=excluded,
            symbol="🚫" if api_cov_config.force_sugar else "[-]",
            style="grey50",
        )

    coverage = compute_coverage(len(covered), len(uncovered))
    status = 0

    if api_cov_config.fail_under is None:
        console.print(f"\n[bold green]Total API Coverage: {coverage}%[/bold green]")
    elif not covered and not uncovered:
        # Every endpoint was excluded: nothing is measurable, so the gate is vacuous.
        console.print(
            f"\n[bold yellow]All {len(excluded)} discovered endpoints are excluded; "
            "coverage requirement not applied.[/bold yellow]"
        )
    elif coverage < api_cov_config.fail_under:
        console.print(
            f"\n[bold red]FAIL: Required coverage of {api_cov_config.fail_under}% not met. "
            f"Actual coverage: {coverage}%[/bold red]"
        )
        status = 1
    else:
        console.print(
            f"\n[bold green]SUCCESS: Coverage of {coverage}% meets requirement of "
            f"{api_cov_config.fail_under}%[/bold green]"
        )

    if api_cov_config.report_path:
        detail = prepare_endpoint_detail(covered + uncovered, called_data)
        final_report = {
            "status": status,
            "coverage": coverage,
            "required_coverage": api_cov_config.fail_under,
            "total_endpoints": len(covered) + len(uncovered),
            "covered_count": len(covered),
            "uncovered_count": len(uncovered),
            "excluded_count": len(excluded),
            "detail": detail,
        }
        write_report_file(final_report, api_cov_config.report_path)
        console.print(f"\n[grey50]JSON report saved to {api_cov_config.report_path}[/grey50]")

    console.print(f"[bold blue]{'=' * (42 + len(' API Coverage Report '))}[/bold blue]\n")
    return status
