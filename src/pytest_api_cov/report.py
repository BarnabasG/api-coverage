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


@lru_cache(maxsize=None)
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


def _split_endpoint(endpoint: str) -> tuple[str | None, str]:
    """Split 'METHOD /path' into (METHOD, path); method is None when absent."""
    if " " in endpoint:
        method, path = endpoint.split(" ", 1)
        return method.upper(), path
    return None, endpoint


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
) -> tuple[_CompiledPatterns, _CompiledPatterns]:
    """Compile and cache exclusion/negation patterns.

    Accepts a tuple (hashable) so the result can be cached across calls.
    """
    exclusions = tuple(_compile_exclusion_pattern(p) for p in patterns if not p.startswith("!"))
    negations = tuple(_compile_exclusion_pattern(p[1:]) for p in patterns if p.startswith("!"))
    return exclusions, negations


def _matches_any(compiled: _CompiledPatterns, method: str | None, path_only: str, endpoint: str) -> bool:
    """Check an endpoint against compiled (methods, regex) patterns."""
    for methods_set, regex in compiled:
        if methods_set and (not method or method not in methods_set):
            continue
        if regex.match(path_only) or regex.match(endpoint):
            return True
    return False


def _partition_excluded(endpoints: list[str], exclusion_patterns: list[str]) -> tuple[list[str], list[str]]:
    """Split endpoints into (kept, excluded); negation patterns override exclusions."""
    if not exclusion_patterns:
        return list(endpoints), []

    compiled_exclusions, compiled_negations = _compile_exclusion_patterns(tuple(exclusion_patterns))
    kept: list[str] = []
    excluded: list[str] = []
    for endpoint in endpoints:
        method, path_only = _split_endpoint(endpoint)
        is_excluded = _matches_any(compiled_exclusions, method, path_only, endpoint) and not _matches_any(
            compiled_negations, method, path_only, endpoint
        )
        (excluded if is_excluded else kept).append(endpoint)
    return kept, excluded


def _match_covered(endpoints: list[str], called_data: dict[str, set[str]]) -> tuple[list[str], list[str]]:
    """Split endpoints into (covered, uncovered) against the recorded call keys."""
    covered: list[str] = []
    uncovered: list[str] = []
    for endpoint in endpoints:
        if contains_escape_characters(endpoint):
            pattern = endpoint_to_regex(endpoint)
            is_covered = any(pattern.match(ep) for ep in called_data)
        else:
            is_covered = endpoint in called_data
        (covered if is_covered else uncovered).append(endpoint)
    return covered, uncovered


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
    kept, excluded = _partition_excluded(endpoints, exclusion_patterns)
    covered, uncovered = _match_covered(kept, called_data)
    return covered, uncovered, excluded


def group_endpoints_by_path(
    endpoints: list[str],
    called_data: dict[str, set[str]],
) -> tuple[list[str], dict[str, set[str]]]:
    """Collapse 'METHOD /path' keys to '/path', merging caller sets across methods."""
    grouped_endpoints = list(dict.fromkeys(_split_endpoint(endpoint)[1] for endpoint in endpoints))

    grouped_calls: dict[str, set[str]] = {}
    for key, callers in called_data.items():
        grouped_calls.setdefault(_split_endpoint(key)[1], set()).update(callers)

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
        # A truthy threshold (> 0) cannot be met without endpoints; an explicit 0 can.
        if api_cov_config.fail_under:
            console.print(
                f"\n[bold red]FAIL: No endpoints discovered but --api-cov-fail-under={api_cov_config.fail_under} "
                "is set. Check your app/client fixtures or OpenAPI spec.[/bold red]"
            )
            return 1
        console.print("\n[bold red]No endpoints discovered. Please check your test setup.[/bold red]")
        return 0

    header = f"{'=' * 20} API Coverage Report {'=' * 20}"
    console.print(f"\n\n[bold blue]{header}[/bold blue]")

    kept, excluded = _partition_excluded(discovered_endpoints, api_cov_config.exclusion_patterns)
    if api_cov_config.group_methods_by_endpoint:
        # Exclusions (possibly method-scoped) apply before methods are collapsed away.
        kept, called_data = group_endpoints_by_path(kept, called_data)
    covered, uncovered = _match_covered(kept, called_data)

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
        # Every endpoint was excluded: nothing is measurable. Fail closed when a
        # real threshold is set, so an over-broad pattern cannot disable the gate.
        if api_cov_config.fail_under:
            console.print(
                f"\n[bold red]FAIL: All {len(excluded)} discovered endpoints are excluded, so no coverage "
                f"can be measured against the requirement of {api_cov_config.fail_under}%. "
                "Loosen the exclusion patterns or remove fail_under.[/bold red]"
            )
            status = 1
        else:
            console.print(
                f"\n[bold yellow]All {len(excluded)} discovered endpoints are excluded; "
                "coverage requirement of 0% is trivially met.[/bold yellow]"
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

    console.print(f"[bold blue]{'=' * len(header)}[/bold blue]\n")
    return status
