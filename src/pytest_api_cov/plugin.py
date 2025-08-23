"""src/pytest_api_cov/plugin.py"""

import importlib
import importlib.util
import logging
import os
from collections import defaultdict
from typing import Any, Optional

import pytest

from .config import get_pytest_api_cov_report_config
from .frameworks import get_framework_adapter
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
    logger.debug("🔍 Auto-discovering app in common locations...")

    # Common file patterns and variable names to check
    common_patterns = [
        ("app.py", ["app", "application", "main"]),
        ("main.py", ["app", "application", "main"]),
        ("server.py", ["app", "application", "server"]),
        ("wsgi.py", ["app", "application"]),
        ("asgi.py", ["app", "application"]),
    ]

    for filename, attr_names in common_patterns:
        if os.path.exists(filename):
            logger.debug(f"🔍 Found {filename}, checking for app variables...")
            try:
                # Import the module
                module_name = filename[:-3]  # Remove .py extension
                spec = importlib.util.spec_from_file_location(module_name, filename)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    # Check each possible app variable name
                    for attr_name in attr_names:
                        if hasattr(module, attr_name):
                            app = getattr(module, attr_name)
                            if is_supported_framework(app):
                                logger.info(
                                    f"✅ Auto-discovered {type(app).__name__} app in {filename} as '{attr_name}'"
                                )
                                return app
                            else:
                                logger.debug(f"🔍 Found '{attr_name}' in {filename} but it's not a supported framework")

            except Exception as e:
                logger.debug(f"🔍 Could not import {filename}: {e}")
                continue

    logger.debug("🔍 No app auto-discovered")
    return None


def get_helpful_error_message() -> str:
    """Generate a helpful error message for setup guidance."""
    return """
🚫 No API app found!

Quick Setup Options:

Option 1 - Auto-discovery (Recommended):
  Place your FastAPI/Flask app in one of these files:
  • app.py (with variable named 'app', 'application', or 'main')
  • main.py (with variable named 'app', 'application', or 'main')
  • server.py (with variable named 'app', 'application', or 'server')

  Example app.py:
    from fastapi import FastAPI
    app = FastAPI()  # <- Plugin will auto-discover this

Option 2 - Manual fixture:
  Create conftest.py with:

    import pytest
    from your_module import your_app

    @pytest.fixture
    def app():
        return your_app

Then run: pytest --api-cov-report

Need help? Run: pytest-api-cov init (for setup wizard)
"""


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add API coverage flags to the pytest parser."""
    add_pytest_api_cov_flags(parser)


def pytest_configure(config: pytest.Config) -> None:
    """Configure the pytest session and logging."""
    # Configure logging based on verbosity level
    if config.getoption("--api-cov-report"):
        verbosity = config.option.verbose

        # Set up logging level based on pytest verbosity
        if verbosity >= 2:  # -vv or more
            log_level = logging.DEBUG
        elif verbosity >= 1:  # -v
            log_level = logging.INFO
        else:  # normal run
            log_level = logging.WARNING

        # Configure the logger
        logger.setLevel(log_level)

        # Only add handler if we don't already have one
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(log_level)
            formatter = logging.Formatter("%(message)s")
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        logger.info("Initializing API coverage plugin...")

    # Register xdist plugin if available
    if config.pluginmanager.hasplugin("xdist"):
        config.pluginmanager.register(DeferXdistPlugin(), "defer_xdist_plugin")


def pytest_sessionstart(session: pytest.Session) -> None:
    """Initialize the call recorder at the start of the session."""
    if session.config.getoption("--api-cov-report"):
        session.api_call_recorder = defaultdict(set)
        session.discovered_endpoints = None


@pytest.fixture
def client(request: pytest.FixtureRequest) -> Any:
    """
    Smart auto-discovering test client that records API calls for coverage.

    Tries to find an 'app' fixture first, then auto-discovers apps in common locations.
    """
    session = request.node.session

    # Only proceed if API coverage is enabled
    if not session.config.getoption("--api-cov-report"):
        pytest.skip("API coverage not enabled. Use --api-cov-report flag.")

    # Try to get app from existing fixture first
    app = None
    try:
        app = request.getfixturevalue("app")
        logger.debug("🔍 Found 'app' fixture")
    except pytest.FixtureLookupError:
        logger.debug("🔍 No 'app' fixture found, trying auto-discovery...")
        app = auto_discover_app()

    # If still no app found, show helpful error
    if app is None:
        helpful_msg = get_helpful_error_message()
        print(helpful_msg)
        pytest.skip("No API app found. See error message above for setup guidance.")

    # Validate the app is supported
    if not is_supported_framework(app):
        pytest.skip(f"Unsupported framework: {type(app).__name__}. pytest-api-coverage supports Flask and FastAPI.")

    try:
        adapter = get_framework_adapter(app)
    except TypeError as e:
        pytest.skip(f"Framework detection failed: {e}")

    recorder = getattr(session, "api_call_recorder", None)

    # Discover endpoints on the first run of this fixture.
    if recorder is not None and getattr(session, "discovered_endpoints", None) is None:
        try:
            session.discovered_endpoints = adapter.get_endpoints()
            logger.info(f"✅ pytest-api-coverage: Discovered {len(session.discovered_endpoints)} endpoints.")
            logger.debug(f"🔍 Discovered endpoints: {session.discovered_endpoints}")
        except Exception as e:
            session.discovered_endpoints = []
            logger.warning(f"⚠️ pytest-api-coverage: Could not discover endpoints. Error: {e}")

    client = adapter.get_tracked_client(recorder, request.node.name)
    yield client


def pytest_sessionfinish(session: pytest.Session) -> None:
    """Generate the API coverage report at the end of the session."""
    if session.config.getoption("--api-cov-report"):
        logger.debug(
            f"📝 pytest-api-coverage: Generating report for {len(getattr(session, 'api_call_recorder', {}))} "
            "recorded endpoints."
        )
        logger.debug(f"🔍 session.config has workeroutput: {hasattr(session.config, 'workeroutput')}")

        if hasattr(session.config, "workeroutput"):
            serializable_recorder = {k: list(v) for k, v in session.api_call_recorder.items()}
            session.config.workeroutput["api_call_recorder"] = serializable_recorder
            # Also send discovered endpoints to master
            session.config.workeroutput["discovered_endpoints"] = getattr(session, "discovered_endpoints", [])
            logger.debug("📤 Sent API call data and discovered endpoints to master process")
        else:
            logger.debug("🔍 No workeroutput found, generating report for master data.")
            master_data = {k: list(v) for k, v in session.api_call_recorder.items()}
            worker_data = getattr(session.config, "worker_api_call_recorder", defaultdict(set))
            logger.debug(f"🔍 Master data: {master_data}")
            logger.debug(f"🔍 Worker data: {dict(worker_data) if worker_data else {}}")

            merged = defaultdict(set)
            if isinstance(worker_data, dict):
                for endpoint, calls in worker_data.items():
                    merged[endpoint].update(calls)
            else:
                merged = worker_data
            for endpoint, calls in master_data.items():
                merged[endpoint].update(calls)

            logger.debug(f"🔍 Merged data: {dict(merged)}")

            # Use worker discovered endpoints if available, fallback to session
            discovered_endpoints = getattr(
                session.config, "worker_discovered_endpoints", getattr(session, "discovered_endpoints", [])
            )
            logger.debug(f"🔍 Using discovered endpoints: {discovered_endpoints}")

            api_cov_config = get_pytest_api_cov_report_config(session.config)
            status = generate_pytest_api_cov_report(
                api_cov_config=api_cov_config,
                called_data=merged,
                discovered_endpoints=discovered_endpoints,
            )
            if session.exitstatus == 0:
                session.exitstatus = status


class DeferXdistPlugin:
    """Simple class to defer pytest-xdist hook until we know it is installed."""

    def pytest_testnodedown(self, node) -> None:
        """Collect API call data from each worker as they finish."""
        logger.debug("🔍 pytest-api-coverage: Worker node down.")
        worker_data = node.workeroutput.get("api_call_recorder")
        discovered_endpoints = node.workeroutput.get("discovered_endpoints", [])
        logger.debug(f"🔍 Worker data: {worker_data}")
        logger.debug(f"🔍 Worker discovered endpoints: {discovered_endpoints}")

        # Merge API call data
        if worker_data:
            logger.debug("🔍 Worker data found, merging with current data.")
            current = getattr(node.config, "worker_api_call_recorder", defaultdict(set))
            logger.debug(f"🔍 Current data before merge: {dict(current) if current else {}}")

            for endpoint, calls in worker_data.items():
                logger.debug(f"🔍 Updating current data with: {endpoint} -> {calls}")
                current[endpoint].update(calls)

            node.config.worker_api_call_recorder = current
            logger.debug(f"🔍 Updated current data: {dict(current)}")

        # Merge discovered endpoints (take the first non-empty list we get)
        if discovered_endpoints and not getattr(node.config, "worker_discovered_endpoints", []):
            node.config.worker_discovered_endpoints = discovered_endpoints
            logger.debug(f"🔍 Set discovered endpoints from worker: {discovered_endpoints}")
