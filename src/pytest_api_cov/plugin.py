"""pytest plugin for API coverage tracking."""

import importlib
import importlib.util
import logging
import os
from typing import Any, Optional

import pytest

from .config import get_pytest_api_cov_report_config
from .frameworks import get_framework_adapter
from .models import SessionData
from .pytest_flags import add_pytest_api_cov_flags
from .report import generate_pytest_api_cov_report

logger = logging.getLogger(__name__)


def is_supported_framework(app: Any) -> bool:
    """Check if the app is a supported framework (Flask or FastAPI)."""
    if app is None:
        return False

    app_type = type(app).__name__
    module_name = getattr(type(app), "__module__", "").split(".")[0]

    return (module_name == "flask" and app_type == "Flask") or (module_name == "fastapi" and app_type == "FastAPI")


def auto_discover_app() -> Optional[Any]:
    """Automatically discover Flask/FastAPI apps in common locations."""
    logger.debug("> Auto-discovering app in common locations...")

    common_patterns = [
        ("app.py", ["app", "application", "main"]),
        ("main.py", ["app", "application", "main"]),
        ("server.py", ["app", "application", "server"]),
        ("wsgi.py", ["app", "application"]),
        ("asgi.py", ["app", "application"]),
    ]

    found_apps = []  # Track all discovered apps
    found_files = []  # Track all files that exist

    for filename, attr_names in common_patterns:
        if os.path.exists(filename):
            found_files.append(filename)
            logger.debug(f"> Found {filename}, checking for app variables...")
            try:
                module_name = filename[:-3]  # .py extension
                spec = importlib.util.spec_from_file_location(module_name, filename)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    for attr_name in attr_names:
                        if hasattr(module, attr_name):
                            app = getattr(module, attr_name)
                            if is_supported_framework(app):
                                found_apps.append((filename, attr_name, type(app).__name__))
                                # Return the first valid app found, but log what we're doing
                                if len(found_apps) == 1:
                                    logger.info(
                                        f"✅ Auto-discovered {type(app).__name__} app in {filename} as '{attr_name}'"
                                    )
                                    # Check if there are more files to scan
                                    remaining_files = [f for f in [p[0] for p in common_patterns[common_patterns.index((filename, attr_names)):]] if os.path.exists(f) and f != filename]
                                    if remaining_files:
                                        logger.debug(f"> Note: Also found files {remaining_files} but using first discovered app")
                                        logger.debug(f"> To use a different app, create a conftest.py with an 'app' fixture")
                                    return app
                            else:
                                logger.debug(f"> Found '{attr_name}' in {filename} but it's not a supported framework")

            except Exception as e:
                logger.debug(f"> Could not import {filename}: {e}")
                continue

    # If we get here, no apps were found
    if found_files:
        logger.debug(f"> Found files {found_files} but no supported Flask/FastAPI apps in them")
        logger.debug(f"> If your app is in one of these files with a different variable name,")
        logger.debug(f"> create a conftest.py with an 'app' fixture to specify it")
    
    logger.debug("> No app auto-discovered")
    return None


def get_helpful_error_message() -> str:
    """Generate a helpful error message for setup guidance."""
    return """
🚫 No API app found!

Quick Setup Options:

Option 1 - Auto-discovery (Zero Config):
  Place your FastAPI/Flask app in one of these files:
  • app.py (with variable named 'app', 'application', or 'main')
  • main.py (with variable named 'app', 'application', or 'main')
  • server.py (with variable named 'app', 'application', or 'server')

  Example app.py:
    from fastapi import FastAPI
    app = FastAPI()  # <- Plugin will auto-discover this

Option 2 - Custom Location or Override Auto-discovery:
  Create conftest.py to specify exactly which app to use:

    import pytest
    from my_project.api.server import my_app  # Any import path!
    # or from app import my_real_app  # Override auto-discovery

    @pytest.fixture
    def app():
        return my_app

  This works for:
  • Apps in custom locations
  • Multiple app files (specify which one to use)
  • Different variable names in standard files

Option 3 - Setup Wizard:
  Run: pytest-api-cov init

Then run: pytest --api-cov-report
"""


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add API coverage flags to the pytest parser."""
    add_pytest_api_cov_flags(parser)


def pytest_configure(config: pytest.Config) -> None:
    """Configure the pytest session and logging."""
    if config.getoption("--api-cov-report"):
        verbosity = config.option.verbose

        if verbosity >= 2:  # -vv or more
            log_level = logging.DEBUG
        elif verbosity >= 1:  # -v
            log_level = logging.INFO
        else:
            log_level = logging.WARNING

        logger.setLevel(log_level)

        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(log_level)
            formatter = logging.Formatter("%(message)s")
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        logger.info("Initializing API coverage plugin...")

    if config.pluginmanager.hasplugin("xdist"):
        config.pluginmanager.register(DeferXdistPlugin(), "defer_xdist_plugin")


def pytest_sessionstart(session: pytest.Session) -> None:
    """Initialize the call recorder at the start of the session."""
    if session.config.getoption("--api-cov-report"):
        session.api_coverage_data = SessionData()  # type: ignore[attr-defined]


def wrap_client_with_coverage(client: Any, recorder: Any, test_name: str) -> Any:
    """Wrap an existing test client with coverage tracking."""

    class CoverageWrapper:
        def __init__(self, wrapped_client: Any):
            self._wrapped = wrapped_client

        def __getattr__(self, name: str) -> Any:
            attr = getattr(self._wrapped, name)
            if name in ["get", "post", "put", "delete", "patch", "head", "options"]:

                def tracked_method(*args: Any, **kwargs: Any) -> Any:
                    response = attr(*args, **kwargs)
                    # Extract path from args[0]
                    if args and recorder is not None:
                        path = args[0]
                        # Clean up the path to match endpoint format
                        if isinstance(path, str):
                            # Remove query parameters
                            path = path.partition("?")[0]
                            recorder.record_call(path, test_name)
                    return response

                return tracked_method
            return attr

    return CoverageWrapper(client)


def get_app_from_fixture_or_auto_discover(request: pytest.FixtureRequest) -> Any:
    """Get app from fixture or auto-discovery."""
    app = None
    try:
        app = request.getfixturevalue("app")
        logger.debug("> Found 'app' fixture")
    except pytest.FixtureLookupError:
        logger.debug("> No 'app' fixture found, trying auto-discovery...")
        app = auto_discover_app()
    return app


@pytest.fixture
def coverage_client(request: pytest.FixtureRequest) -> Any:
    """
    Smart auto-discovering test coverage_client that records API calls for coverage.

    Tries to find an 'app' fixture first, then auto-discovers apps in common locations.
    Can also wrap existing custom fixtures if configured.
    """
    session = request.node.session

    if not session.config.getoption("--api-cov-report"):
        pytest.skip("API coverage not enabled. Use --api-cov-report flag.")

    config = get_pytest_api_cov_report_config(request.config)
    coverage_data = getattr(session, "api_coverage_data", None)
    if coverage_data is None:
        pytest.skip("API coverage data not initialized. This should not happen.")

    # Check if we should wrap an existing fixture
    if config.client_fixture_name != "coverage_client":
        try:
            # Get the existing custom fixture
            existing_client = request.getfixturevalue(config.client_fixture_name)
            logger.info(f"> Found custom fixture '{config.client_fixture_name}', wrapping with coverage tracking")

            # We still need to discover endpoints, so try to get the app
            app = get_app_from_fixture_or_auto_discover(request)
            if app and is_supported_framework(app):
                try:
                    adapter = get_framework_adapter(app)
                    if not coverage_data.discovered_endpoints.endpoints:
                        endpoints = adapter.get_endpoints()
                        framework_name = type(app).__name__
                        for endpoint in endpoints:
                            coverage_data.add_discovered_endpoint(endpoint, f"{framework_name.lower()}_adapter")
                        logger.info(f"> pytest-api-coverage: Discovered {len(endpoints)} endpoints.")
                        logger.debug(f"> Discovered endpoints: {endpoints}")
                except Exception as e:
                    logger.warning(f"> pytest-api-coverage: Could not discover endpoints from app. Error: {e}")

            # Wrap the existing client with coverage tracking
            wrapped_client = wrap_client_with_coverage(existing_client, coverage_data.recorder, request.node.name)
            yield wrapped_client
            return

        except pytest.FixtureLookupError:
            logger.warning(f"> Custom fixture '{config.client_fixture_name}' not found, falling back to auto-discovery")

    # Original auto-discovery logic
    app = get_app_from_fixture_or_auto_discover(request)

    if app is None:
        helpful_msg = get_helpful_error_message()
        print(helpful_msg)
        pytest.skip("No API app found. See error message above for setup guidance.")

    if not is_supported_framework(app):
        pytest.skip(f"Unsupported framework: {type(app).__name__}. pytest-api-coverage supports Flask and FastAPI.")

    try:
        adapter = get_framework_adapter(app)
    except TypeError as e:
        pytest.skip(f"Framework detection failed: {e}")

    if not coverage_data.discovered_endpoints.endpoints:
        try:
            endpoints = adapter.get_endpoints()
            framework_name = type(app).__name__
            for endpoint in endpoints:
                coverage_data.add_discovered_endpoint(endpoint, f"{framework_name.lower()}_adapter")
            logger.info(f"> pytest-api-coverage: Discovered {len(endpoints)} endpoints.")
            logger.debug(f"> Discovered endpoints: {endpoints}")
        except Exception as e:
            logger.warning(f"> pytest-api-coverage: Could not discover endpoints. Error: {e}")

    client = adapter.get_tracked_client(coverage_data.recorder, request.node.name)
    yield client


def pytest_sessionfinish(session: pytest.Session) -> None:
    """Generate the API coverage report at the end of the session."""
    if session.config.getoption("--api-cov-report"):
        coverage_data = getattr(session, "api_coverage_data", None)
        if coverage_data is None:
            logger.warning("> No API coverage data found. Plugin may not have been properly initialized.")
            return

        logger.debug(f"> pytest-api-coverage: Generating report for {len(coverage_data.recorder)} recorded endpoints.")
        if hasattr(session.config, "workeroutput"):
            serializable_recorder = coverage_data.recorder.to_serializable()
            session.config.workeroutput["api_call_recorder"] = serializable_recorder
            session.config.workeroutput["discovered_endpoints"] = coverage_data.discovered_endpoints.endpoints
            logger.debug("> Sent API call data and discovered endpoints to master process")
        else:
            logger.debug("> No workeroutput found, generating report for master data.")

            worker_recorder_data = getattr(session.config, "worker_api_call_recorder", {})
            worker_endpoints = getattr(session.config, "worker_discovered_endpoints", [])

            # Merge worker data into session data
            if worker_recorder_data or worker_endpoints:
                coverage_data.merge_worker_data(worker_recorder_data, worker_endpoints)
                logger.debug(f"> Merged worker data: {len(worker_recorder_data)} endpoints")

            logger.debug(f"> Final merged data: {len(coverage_data.recorder)} recorded endpoints")
            logger.debug(f"> Using discovered endpoints: {coverage_data.discovered_endpoints.endpoints}")

            api_cov_config = get_pytest_api_cov_report_config(session.config)
            status = generate_pytest_api_cov_report(
                api_cov_config=api_cov_config,
                called_data=coverage_data.recorder.calls,
                discovered_endpoints=coverage_data.discovered_endpoints.endpoints,
            )
            if session.exitstatus == 0:
                session.exitstatus = status

        if hasattr(session, "api_coverage_data"):
            delattr(session, "api_coverage_data")

        if hasattr(session.config, "worker_api_call_recorder"):
            delattr(session.config, "worker_api_call_recorder")


class DeferXdistPlugin:
    """Simple class to defer pytest-xdist hook until we know it is installed."""

    def pytest_testnodedown(self, node: Any) -> None:
        """Collect API call data from each worker as they finish."""
        logger.debug("> pytest-api-coverage: Worker node down.")
        worker_data = node.workeroutput.get("api_call_recorder", {})
        discovered_endpoints = node.workeroutput.get("discovered_endpoints", [])
        logger.debug(f"> Worker data: {worker_data}")
        logger.debug(f"> Worker discovered endpoints: {discovered_endpoints}")

        # Merge API call data
        if worker_data:
            logger.debug("> Worker data found, merging with current data.")
            current = getattr(node.config, "worker_api_call_recorder", {})
            logger.debug(f"> Current data before merge: {current}")

            # Merge the worker data into current
            for endpoint, calls in worker_data.items():
                if endpoint not in current:
                    current[endpoint] = set()
                elif not isinstance(current[endpoint], set):
                    current[endpoint] = set(current[endpoint])
                current[endpoint].update(calls)
                logger.debug(f"> Updated endpoint {endpoint} with calls: {calls}")

            node.config.worker_api_call_recorder = current
            logger.debug(f"> Updated current data: {current}")

        if discovered_endpoints and not getattr(node.config, "worker_discovered_endpoints", []):
            node.config.worker_discovered_endpoints = discovered_endpoints
            logger.debug(f"> Set discovered endpoints from worker: {discovered_endpoints}")
