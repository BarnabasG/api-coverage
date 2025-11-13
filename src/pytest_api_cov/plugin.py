"""pytest plugin for API coverage tracking."""

import logging
from typing import Any, Optional, Tuple

import pytest

from .config import get_pytest_api_cov_report_config
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

    return (
        (module_name == "flask" and app_type == "Flask")
        or (module_name == "flask_openapi3" and app_type == "OpenAPI")
        or (module_name == "fastapi" and app_type == "FastAPI")
    )


def extract_app_from_client(client: Any) -> Optional[Any]:
    """Extract app from various client types."""
    # Typical attributes used by popular clients
    if client is None:
        return None

    # common attribute for requests-like test clients
    if hasattr(client, "app"):
        return client.app

    if hasattr(client, "application"):
        return client.application

    # Starlette/requests transport internals
    if hasattr(client, "_transport") and hasattr(client._transport, "app"):
        return client._transport.app

    # Flask's test client may expose the application via "application" or "app"
    if hasattr(client, "_app"):
        return client._app

    return None


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


def create_coverage_fixture(fixture_name: str, existing_fixture_name: Optional[str] = None) -> Any:
    """Create a coverage-enabled fixture with a custom name.

    Args:
        fixture_name: The name for the new fixture
        existing_fixture_name: Optional name of existing fixture to wrap

    Returns:
        A pytest fixture function that can be used in conftest.py

    Example usage in conftest.py:
        import pytest
        from pytest_api_cov.plugin import create_coverage_fixture

        # Create a new fixture
        my_client = create_coverage_fixture('my_client')

        # Wrap an existing fixture
        flask_client = create_coverage_fixture('flask_client', 'original_flask_client')

    """

    def fixture_func(request: pytest.FixtureRequest) -> Any:
        """Coverage-enabled client fixture."""
        session = request.node.session

        # Do not skip tests; if coverage is disabled or not initialized, try to return an existing client
        coverage_enabled = bool(session.config.getoption("--api-cov-report"))

        coverage_data = getattr(session, "api_coverage_data", None)

        # Try to obtain an existing client if requested
        existing_client = None
        if existing_fixture_name:
            try:
                existing_client = request.getfixturevalue(existing_fixture_name)
                logger.debug(f"> Found existing '{existing_fixture_name}' fixture, wrapping with coverage")
            except pytest.FixtureLookupError:
                logger.warning(f"> Existing fixture '{existing_fixture_name}' not found when creating '{fixture_name}'")

        # If coverage is not enabled or recorder not available, return existing client (if any)
        if not coverage_enabled or coverage_data is None:
            if existing_client is not None:
                yield existing_client
                return
            # Try to fall back to an app fixture to construct a client
            try:
                app = request.getfixturevalue("app")
            except pytest.FixtureLookupError:
                logger.warning(
                    f"> Coverage not enabled and no existing fixture available for '{fixture_name}', returning None"
                )
                yield None
                return
            # if we have an app, attempt to create a tracked client using adapter without recorder
            try:
                from .frameworks import get_framework_adapter

                adapter = get_framework_adapter(app)
                client = adapter.get_tracked_client(None, request.node.name)
            except Exception:  # noqa: BLE001
                yield existing_client
                return
            else:
                yield client
                return

        # At this point coverage is enabled and coverage_data exists
        if existing_client is None:
            # Try to find a client fixture by common names
            config = get_pytest_api_cov_report_config(request.config)
            for name in config.client_fixture_names:
                try:
                    existing_client = request.getfixturevalue(name)
                    logger.info(f"> Found client fixture '{name}' while creating '{fixture_name}'")
                    break
                except pytest.FixtureLookupError:
                    continue

        app = None
        if existing_client is not None:
            app = extract_app_from_client(existing_client)

        if app is None:
            # Try to get an app fixture
            try:
                app = request.getfixturevalue("app")
                logger.debug("> Found 'app' fixture while creating coverage fixture")
            except pytest.FixtureLookupError:
                app = None

        if app and is_supported_framework(app):
            try:
                from .frameworks import get_framework_adapter

                adapter = get_framework_adapter(app)
                if not coverage_data.discovered_endpoints.endpoints:
                    endpoints = adapter.get_endpoints()
                    framework_name = type(app).__name__
                    for endpoint_method in endpoints:
                        method, path = endpoint_method.split(" ", 1)
                        coverage_data.add_discovered_endpoint(path, method, f"{framework_name.lower()}_adapter")
                    logger.info(
                        f"> pytest-api-coverage: Discovered {len(endpoints)} endpoints when creating '{fixture_name}'."
                    )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"> pytest-api-coverage: Could not discover endpoints from app. Error: {e}")

        # If we have an existing client, wrap it; otherwise try to create a tracked client from app
        if existing_client is not None:
            wrapped = wrap_client_with_coverage(existing_client, coverage_data.recorder, request.node.name)
            yield wrapped
            return

        if app is not None:
            try:
                from .frameworks import get_framework_adapter

                adapter = get_framework_adapter(app)
                client = adapter.get_tracked_client(coverage_data.recorder, request.node.name)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"> Failed to create tracked client for '{fixture_name}': {e}")
            else:
                yield client
                return

        # Last resort: yield None but do not skip
        logger.warning(
            f"> create_coverage_fixture('{fixture_name}') could not provide a client; "
            "tests will run without API coverage for this fixture."
        )
        yield None

    fixture_func.__name__ = fixture_name
    return pytest.fixture(fixture_func)


def wrap_client_with_coverage(client: Any, recorder: Any, test_name: str) -> Any:
    """Wrap an existing test client with coverage tracking."""
    if client is None or recorder is None:
        return client

    class CoverageWrapper:
        def __init__(self, wrapped_client: Any) -> None:
            self._wrapped = wrapped_client

        def _extract_path_and_method(self, name: str, args: Any, kwargs: Any) -> Optional[Tuple[str, str]]:
            # Try several strategies to obtain a path and method
            path = None
            method = None

            # First, if args[0] looks like a string path
            if args:
                first = args[0]
                if isinstance(first, str):
                    path = first.partition("?")[0]
                    method = kwargs.get("method", name).upper()
                    if method == "OPEN":
                        method = "GET"

                    return path, method

                # For starlette/requests TestClient, args[0] may be a Request or PreparedRequest
                if hasattr(first, "url") and hasattr(first.url, "path"):
                    try:
                        path = first.url.path
                        method = getattr(first, "method", name).upper()
                    except Exception:  # noqa: BLE001
                        pass
                    else:
                        return path, method

            if kwargs:
                path_kw = kwargs.get("path") or kwargs.get("url") or kwargs.get("uri")
                if isinstance(path_kw, str):
                    path = path_kw.partition("?")[0]
                    method = kwargs.get("method", name).upper()
                    if method == "OPEN":
                        method = "GET"

                    return path, method

            return None

        def __getattr__(self, name: str) -> Any:
            attr = getattr(self._wrapped, name)
            if name in {"get", "post", "put", "delete", "patch", "head", "options"}:

                def tracked_method(*args: Any, **kwargs: Any) -> Any:
                    response = attr(*args, **kwargs)
                    if recorder is not None:
                        pm = self._extract_path_and_method(name, args, kwargs)
                        if pm:
                            path, method = pm
                            recorder.record_call(path, test_name, method)
                    return response

                return tracked_method

            if name == "open":

                def tracked_open(*args: Any, **kwargs: Any) -> Any:
                    response = attr(*args, **kwargs)
                    if recorder is not None:
                        pm = self._extract_path_and_method("OPEN", args, kwargs)
                        if pm:
                            path, method = pm
                            recorder.record_call(path, test_name, method)
                    return response

                return tracked_open

            return attr

    return CoverageWrapper(client)


@pytest.fixture
def coverage_client(request: pytest.FixtureRequest) -> Any:
    """Smart  client fixture that wrap's user's existing test client with coverage tracking."""
    session = request.node.session

    if not session.config.getoption("--api-cov-report"):
        pytest.skip("API coverage not enabled. Use --api-cov-report flag.")

    config = get_pytest_api_cov_report_config(request.config)
    coverage_data = getattr(session, "api_coverage_data", None)
    if coverage_data is None:
        pytest.skip("API coverage data not initialized. This should not happen.")

    client = None
    for fixture_name in config.client_fixture_names:
        try:
            client = request.getfixturevalue(fixture_name)
            logger.info(f"> Found custom fixture '{fixture_name}', wrapping with coverage tracking")
            break
        except pytest.FixtureLookupError:
            logger.debug(f"> Custom fixture '{fixture_name}' not found, trying next one")
            continue

    if client is None:
        # Try to fallback to an 'app' fixture and create a tracked client
        try:
            app = request.getfixturevalue("app")
            logger.info("> Found 'app' fixture, creating tracked client from app")
            from .frameworks import get_framework_adapter

            adapter = get_framework_adapter(app)
            client = adapter.get_tracked_client(coverage_data.recorder, request.node.name)
        except pytest.FixtureLookupError:
            logger.warning("> No test client fixture found and no 'app' fixture available. Falling back to None")
            client = None
        except Exception as e:  # noqa: BLE001
            logger.warning(f"> Failed to create tracked client from 'app' fixture: {e}")
            client = None

    if client is None:
        logger.warning("> Coverage client could not be created; tests will run without API coverage for this session.")
        return None

    app = extract_app_from_client(client)
    logger.debug(f"> Extracted app from client: {app}, app type: {type(app).__name__ if app else None}")

    if app is None:
        logger.warning("> No app found, returning client without coverage tracking")
        return client

    if not is_supported_framework(app):
        logger.warning(
            f"> Unsupported framework: {type(app).__name__}. pytest-api-coverage supports Flask and FastAPI."
        )
        return client

    try:
        from .frameworks import get_framework_adapter

        adapter = get_framework_adapter(app)
        logger.debug(f"> Got adapter: {adapter}, adapter type: {type(adapter).__name__ if adapter else None}")
    except TypeError as e:
        logger.warning(f"> Framework detection failed: {e}")
        return client

    if not coverage_data.discovered_endpoints.endpoints:
        try:
            endpoints = adapter.get_endpoints()
            logger.debug(f"> Adapter returned {len(endpoints)} endpoints")
            framework_name = type(app).__name__
            for endpoint_method in endpoints:
                method, path = endpoint_method.split(" ", 1)
                coverage_data.add_discovered_endpoint(path, method, f"{framework_name.lower()}_adapter")
            logger.info(f"> pytest-api-coverage: Discovered {len(endpoints)} endpoints.")
            logger.debug(f"> Discovered endpoints: {endpoints}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"> pytest-api-coverage: Could not discover endpoints. Error: {e}")
            return client

    return wrap_client_with_coverage(client, coverage_data.recorder, request.node.name)


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
