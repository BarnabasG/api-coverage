"""src/pytest_api_cov/report.py: Generates the API coverage report output."""

import json
import re
from collections import defaultdict
from pathlib import Path
from re import Pattern
from typing import Any, Dict, List, Set, Tuple

from rich.console import Console

from .config import ApiCoverageReportConfig


def endpoint_to_regex(endpoint: str) -> Pattern[str]:
    """Create a regex pattern from an endpoint by replacing dynamic segments."""
    placeholder = "___PLACEHOLDER___"
    temp_endpoint = re.escape(re.sub(r"<[^>]+>|\{[^}]+\}", placeholder, endpoint))
    return re.compile("^" + temp_endpoint.replace(placeholder, "(.+)") + "$")


def contains_escape_characters(endpoint: str) -> bool:
    """Escape special characters in the endpoint string."""
    return ("<" in endpoint and ">" in endpoint) or ("{" in endpoint and "}" in endpoint)


def categorise_endpoints(
    endpoints: List[str],
    called_data: Dict[str, Set[str]],
    exclusion_patterns: List[str],
) -> Tuple[List[str], List[str], List[str]]:
    """Categorise endpoints into covered, uncovered, and excluded."""
    covered, uncovered, excluded = [], [], []
    regex_exclusion_patterns = re.compile("|".join(map(re.escape, exclusion_patterns))) if exclusion_patterns else None
    for endpoint in endpoints:
        if regex_exclusion_patterns and regex_exclusion_patterns.search(endpoint):
            excluded.append(endpoint)
            continue
        elif contains_escape_characters(endpoint):
            pattern = endpoint_to_regex(endpoint)
            is_covered = any(pattern.match(ep) for ep in called_data)
        else:
            is_covered = endpoint in called_data
        covered.append(endpoint) if is_covered else uncovered.append(endpoint)
    return covered, uncovered, excluded


def print_endpoints(
    console: Console,
    label: str,
    endpoints: List[str],
    symbol: str,
    style: str,
) -> None:
    """Prints a list of endpoints to the console with a label and style."""
    if endpoints:
        console.print(f"[{style}]{label}[/]:")
        for endpoint in endpoints:
            console.print(f"  {symbol} [{style}]{endpoint}[/]")


def compute_coverage(covered_count: int, uncovered_count: int) -> float:
    """Compute API coverage percentage."""
    total = covered_count + uncovered_count
    return round(100 * covered_count / total, 2) if total > 0 else 0.0


def prepare_endpoint_detail(endpoints: List[str], called_data: Dict[str, Set[str]]) -> List[Dict[str, Any]]:
    """Prepare endpoint details by mapping each endpoint to its callers."""
    details = []
    for endpoint in endpoints:
        if contains_escape_characters(endpoint):
            pattern = endpoint_to_regex(endpoint)
            callers = set()
            for call in called_data:
                if pattern.match(call):
                    callers.update(called_data[call])
        else:
            callers = called_data.get(endpoint, set())
        details.append({"endpoint": endpoint, "callers": sorted(list(callers))})
    return sorted(details, key=lambda x: len(x["callers"]))


def write_report_file(report_data: Dict[str, Any], report_path: str) -> None:
    """Write the report data to a JSON file."""
    path = Path(report_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(report_data, f, indent=2)


def generate_pytest_api_cov_report(
    api_cov_config: ApiCoverageReportConfig,
    called_data: Dict[str, Set[str]],
    discovered_endpoints: List[str],
) -> int:
    """Generate and print the API coverage report, returning an exit status."""

    console = Console()

    if not discovered_endpoints:
        console.print("\n[bold red]No endpoints discovered. Please check your test setup.[/bold red]")
        return 0

    separator = "=" * 20
    console.print(f"\n\n[bold blue]{separator} API Coverage Report {separator}[/bold blue]")

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
        detail = prepare_endpoint_detail(covered + uncovered, called_data)  # type: ignore[arg-type]
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
