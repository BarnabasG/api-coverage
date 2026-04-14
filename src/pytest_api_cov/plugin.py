"""pytest plugin for API coverage tracking."""

import logging
from typing import Any

import pytest

from .config import ApiCoverageReportConfig, get_pytest_api_cov_report_config
from .frameworks import get_framework_adapter, is_supported_framework
from .models import SessionData
from .openapi import parse_openapi_spec
from .pytest_flags import add_pytest_api_cov_flags
from .report import generate_pytest_api_cov_report

logger = logging.getLogger(__name__)


def _discover_openapi_endpoints(config: ApiCoverageReportConfig, coverage_data: SessionData) -> None:
    """Discover endpoints from OpenAPI spec if configured."""
    if not config.openapi_spec or coverage_data.discovered_endpoints.endpoints:
        return

    endpoints = parse_openapi_spec(config.openapi_spec)
    if not endpoints:
        logger.warning(f"> No endpoints found in OpenAPI spec: {config.openapi_spec}")
        return

    for endpoint_method in endpoints:
        method, path = endpoint_method.split(" ", 1)
        coverage_data.add_discovered_endpoint(path, method, "openapi_spec")

    logger.info(f"> Discovered {len(endpoints)} endpoints from OpenAPI spec: {config.openapi_spec}")


def _discover_app_endpoints(app: Any, coverage_data: SessionData, fixture_name: str) -> None:
    """Discover endpoints from the app instance."""
    if not (app and is_supported_framework(app) and not coverage_data.discovered_endpoints.endpoints):
        return

    try:
        adapter = get_framework_adapter(app)
        endpoints = adapter.get_endpoints()
        framework_name = type(app).__name__

        for endpoint_method in endpoints:
            method, path = endpoint_method.split(" ", 1)
            coverage_data.add_discovered_endpoint(path, method, f"{framework_name.lower()}_adapter")

        logger.info(f"> Discovered {len(endpoints)} endpoints for '{fixture_name}'")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"> Failed to discover endpoints from app: {e}")


def extract_app_from_client(client: Any) -> Any | None:
    """Extract app from various test client types."""
    if client is None:
        return None

    if hasattr(client, "app"):
        return client.app

    if hasattr(client, "application"):
        return client.application

    # Starlette/httpx transport internals
    if hasattr(client, "_transport") and hasattr(client._transport, "app"):
        return client._transport.app

    if hasattr(client, "_app"):
        return client._app

    return getattr(client, "handler", None)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add API coverage flags to the pytest parser."""
    add_pytest_api_cov_flags(parser)


def pytest_configure(config: pytest.Config) -> None:
    """Configure the pytest session and logging."""
    if config.getoption("--api-cov-report"):
        verbosity = config.option.verbose

        if verbosity >= 2:
            log_level = logging.DEBUG
        elif verbosity >= 1:
            log_level = logging.INFO
        else:
            log_level = logging.WARNING

        logger.setLevel(log_level)
        logger.info("Initializing API coverage plugin...")

    if config.pluginmanager.hasplugin("xdist"):
        config.pluginmanager.register(DeferXdistPlugin(), "defer_xdist_plugin")


def pytest_sessionstart(session: pytest.Session) -> None:
    """Initialize coverage data at session start."""
    if session.config.getoption("--api-cov-report"):
        session.api_coverage_data = SessionData()  # type: ignore[attr-defined]


def _try_get_fixture(request: pytest.FixtureRequest, names: tuple[str, ...] | list[str]) -> Any | None:
    """Try fixture names in order, return the first found or None."""
    for name in names:
        try:
            return request.getfixturevalue(name)
        except pytest.FixtureLookupError:  # noqa: PERF203
            continue
    return None


def create_coverage_fixture(fixture_name: str, existing_fixture_name: str | None = None) -> Any:
    """Create a coverage-enabled fixture with a custom name.

    Example::

        my_client = create_coverage_fixture('my_client')
        flask_client = create_coverage_fixture('flask_client', 'original_flask_client')
    """

    def fixture_func(request: pytest.FixtureRequest) -> Any:
        """Coverage-enabled client fixture."""
        session = request.node.session

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

        # Without coverage, just pass through the existing client
        if not coverage_enabled or coverage_data is None:
            if existing_client is not None:
                yield existing_client
                return
            try:
                app = request.getfixturevalue("app")
            except pytest.FixtureLookupError:
                logger.warning(
                    f"> Coverage not enabled and no existing fixture available for '{fixture_name}', returning None"
                )
                yield None
                return
            try:
                adapter = get_framework_adapter(app)
                client = adapter.get_tracked_client(None, request.node.name)
            except Exception:  # noqa: BLE001
                yield existing_client
                return
            else:
                yield client
                return

        config = get_pytest_api_cov_report_config(request.config)
        _discover_openapi_endpoints(config, coverage_data)

        if existing_client is None:
            for name in config.client_fixture_names:
                try:
                    existing_client = request.getfixturevalue(name)
                    logger.info(f"> Found client fixture '{name}' for '{fixture_name}'")
                    break
                except pytest.FixtureLookupError:
                    continue

        app = None
        if existing_client is not None:
            app = extract_app_from_client(existing_client)

        if app is None:
            try:
                app = request.getfixturevalue("app")
            except pytest.FixtureLookupError:
                app = None

        _discover_app_endpoints(app, coverage_data, fixture_name)

        if existing_client is not None:
            wrapped = wrap_client_with_coverage(existing_client, coverage_data.recorder, request.node.name)
            yield wrapped
            return

        if app is not None:
            try:
                adapter = get_framework_adapter(app)
                client = adapter.get_tracked_client(coverage_data.recorder, request.node.name)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"> Failed to create tracked client for '{fixture_name}': {e}")
            else:
                yield client
                return

        # Last resort - yield None but don't skip, so tests still run
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

        _TRACKED_NAMES = frozenset({"get", "post", "put", "delete", "patch", "head", "options", "request", "open"})

        def _extract_path_and_method(self, name: str, args: Any, kwargs: Any) -> tuple[str, str] | None:
            """Pull path and HTTP method from the call arguments."""
            # .request(method, url, ...) - method is first arg, url is second
            if name == "request":
                req_method = (args[0] if args else kwargs.get("method", "GET")).upper()
                req_url = args[1] if len(args) > 1 else kwargs.get("url")
                if isinstance(req_url, str):
                    return req_url if "?" not in req_url else req_url.partition("?")[0], req_method
                return None

            # .get(url), .post(url), .open(url), etc. - url is first arg
            if args:
                first = args[0]
                if isinstance(first, str):
                    path = first if "?" not in first else first.partition("?")[0]
                    method = kwargs.get("method", name).upper()
                    return path, ("GET" if method == "OPEN" else method)

                if hasattr(first, "url") and hasattr(first.url, "path"):
                    try:
                        return first.url.path, getattr(first, "method", name).upper()
                    except Exception:  # noqa: BLE001
                        pass

            if kwargs:
                path_kw = kwargs.get("path") or kwargs.get("url") or kwargs.get("uri")
                if isinstance(path_kw, str):
                    path = path_kw if "?" not in path_kw else path_kw.partition("?")[0]
                    method = kwargs.get("method", name).upper()
                    return path, ("GET" if method == "OPEN" else method)

            return None

        def __getattr__(self, name: str) -> Any:
            attr = getattr(self._wrapped, name)
            if name not in self._TRACKED_NAMES:
                return attr

            def tracked(*args: Any, **kwargs: Any) -> Any:
                response = attr(*args, **kwargs)
                if recorder is not None:
                    pm = self._extract_path_and_method(name, args, kwargs)
                    if pm:
                        path, method = pm
                        recorder.record_call(path, test_name, method)
                return response

            object.__setattr__(self, name, tracked)
            return tracked

    return CoverageWrapper(client)


def _coverage_client_impl(request: pytest.FixtureRequest) -> Any:
    """Inner generator shared by coverage_client and create_coverage_fixture."""
    session = request.node.session

    coverage_enabled = bool(session.config.getoption("--api-cov-report"))
    coverage_data = getattr(session, "api_coverage_data", None)

    if not coverage_enabled or coverage_data is None:
        # Try common client fixture names then app fixture
        found = _try_get_fixture(request, ("client", "test_client", "api_client", "app_client"))
        if found is not None:
            yield found
            return
        try:
            app = request.getfixturevalue("app")
            adapter = get_framework_adapter(app)
        except (pytest.FixtureLookupError, Exception):  # noqa: BLE001
            yield None
        else:
            yield adapter.get_tracked_client(None, request.node.name)
        return

    config = get_pytest_api_cov_report_config(request.config)
    _discover_openapi_endpoints(config, coverage_data)

    # Find a client fixture
    client = _try_get_fixture(request, config.client_fixture_names)
    if client is not None:
        logger.info("> Found client fixture")

    app = extract_app_from_client(client) if client else None
    if app is None:
        try:
            app = request.getfixturevalue("app")
        except pytest.FixtureLookupError:
            app = None

    _discover_app_endpoints(app, coverage_data, "coverage_client")

    if client is not None:
        yield wrap_client_with_coverage(client, coverage_data.recorder, request.node.name)
        return

    if app is not None:
        try:
            adapter = get_framework_adapter(app)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"> Failed to create tracked client: {e}")
        else:
            yield adapter.get_tracked_client(coverage_data.recorder, request.node.name)
            return

    logger.warning("> coverage_client could not provide a client; tests will run without API coverage.")
    yield None


@pytest.fixture
def coverage_client(request: pytest.FixtureRequest) -> Any:
    """Smart client fixture that wraps the user's test client with coverage tracking."""
    yield from _coverage_client_impl(request)


def pytest_sessionfinish(session: pytest.Session) -> None:
    """Generate the API coverage report at session end."""
    if session.config.getoption("--api-cov-report"):
        coverage_data = getattr(session, "api_coverage_data", None)
        if coverage_data is None:
            logger.warning("> No API coverage data found. Plugin may not have been properly initialized.")
            return

        logger.debug(f"> Generating report for {len(coverage_data.recorder)} recorded endpoints.")
        if hasattr(session.config, "workeroutput"):
            serializable_recorder = coverage_data.recorder.to_serializable()
            session.config.workeroutput["api_call_recorder"] = serializable_recorder
            session.config.workeroutput["discovered_endpoints"] = coverage_data.discovered_endpoints.endpoints
            logger.debug("> Sent API call data and discovered endpoints to master process")
        else:
            worker_recorder_data = getattr(session.config, "worker_api_call_recorder", {})
            worker_endpoints = getattr(session.config, "worker_discovered_endpoints", [])

            if worker_recorder_data or worker_endpoints:
                coverage_data.merge_worker_data(worker_recorder_data, worker_endpoints)
                logger.debug(f"> Merged worker data: {len(worker_recorder_data)} endpoints")

            logger.debug(f"> Final merged data: {len(coverage_data.recorder)} recorded endpoints")

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
    """Defers pytest-xdist hook until we know it is installed."""

    def pytest_testnodedown(self, node: Any) -> None:
        """Collect API call data from each worker as they finish."""
        logger.debug("> Worker node down.")
        worker_data = node.workeroutput.get("api_call_recorder", {})
        discovered_endpoints = node.workeroutput.get("discovered_endpoints", [])

        if worker_data:
            current = getattr(node.config, "worker_api_call_recorder", {})

            for endpoint, calls in worker_data.items():
                current.setdefault(endpoint, set()).update(calls)

            node.config.worker_api_call_recorder = current

        if discovered_endpoints and not getattr(node.config, "worker_discovered_endpoints", []):
            node.config.worker_discovered_endpoints = discovered_endpoints
            logger.debug(f"> Set discovered endpoints from worker: {discovered_endpoints}")
