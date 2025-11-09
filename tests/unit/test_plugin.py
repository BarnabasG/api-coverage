"""Tests for the pytest plugin."""

from collections import defaultdict
from unittest.mock import Mock, patch

import pytest

from pytest_api_cov.models import SessionData
from pytest_api_cov.plugin import (
    DeferXdistPlugin,
    is_supported_framework,
    pytest_addoption,
    pytest_configure,
    pytest_sessionfinish,
    pytest_sessionstart,
    extract_app_from_client,
    wrap_client_with_coverage,
    create_coverage_fixture,
)


class TestSupportedFramework:
    """Tests for framework detection utility functions."""

    def test_is_supported_framework_none(self):
        """Test framework detection with None."""
        assert is_supported_framework(None) is False

    def test_is_supported_framework_flask(self):
        """Test framework detection with Flask app."""
        mock_app = Mock()
        mock_app.__class__.__name__ = "Flask"
        mock_app.__class__.__module__ = "flask.app"
        assert is_supported_framework(mock_app) is True

    def test_is_supported_framework_fastapi(self):
        """Test framework detection with FastAPI app."""
        mock_app = Mock()
        mock_app.__class__.__name__ = "FastAPI"
        mock_app.__class__.__module__ = "fastapi.applications"
        assert is_supported_framework(mock_app) is True

    def test_is_supported_framework_unsupported(self):
        """Test framework detection with unsupported framework."""
        mock_app = Mock()
        mock_app.__class__.__name__ = "Django"
        mock_app.__class__.__module__ = "django.core"
        assert is_supported_framework(mock_app) is False


class TestPluginHooks:
    """Tests for pytest plugin hooks."""

    def test_pytest_addoption(self):
        """Test that pytest_addoption adds the required flags."""
        mock_parser = Mock()

        pytest_addoption(mock_parser)

        assert callable(pytest_addoption)

    def test_pytest_sessionstart_with_api_cov_report(self):
        """Test pytest_sessionstart when --api-cov-report is enabled."""
        mock_session = Mock()
        mock_session.config.getoption.return_value = True

        pytest_sessionstart(mock_session)

        assert hasattr(mock_session, "api_coverage_data")
        assert mock_session.api_coverage_data is not None
        assert hasattr(mock_session.api_coverage_data, "recorder")
        assert hasattr(mock_session.api_coverage_data, "discovered_endpoints")

    def test_pytest_sessionstart_without_api_cov_report(self):
        """Test pytest_sessionstart when --api-cov-report is disabled."""

        class SimpleSession:
            def __init__(self):
                self.config = Mock()
                self.config.getoption.return_value = False

        mock_session = SimpleSession()

        pytest_sessionstart(mock_session)

        assert not hasattr(mock_session, "api_coverage_data")

    @patch("pytest_api_cov.plugin.get_pytest_api_cov_report_config")
    @patch("pytest_api_cov.plugin.generate_pytest_api_cov_report")
    def test_pytest_sessionfinish_with_api_cov_report(self, mock_generate_report, mock_get_config):
        """Test pytest_sessionfinish when --api-cov-report is enabled."""
        mock_session = Mock()
        mock_session.config.getoption.side_effect = lambda flag: flag == "--api-cov-report"

        coverage_data = SessionData()
        coverage_data.recorder.record_call("/test", "test_func")
        coverage_data.discovered_endpoints.endpoints = ["/test"]
        mock_session.api_coverage_data = coverage_data
        mock_session.exitstatus = 0

        del mock_session.config.workeroutput
        mock_session.config.worker_api_call_recorder = {}
        mock_session.config.worker_discovered_endpoints = []

        mock_config = Mock()
        mock_get_config.return_value = mock_config
        mock_generate_report.return_value = 1

        pytest_sessionfinish(mock_session)

        mock_get_config.assert_called_once_with(mock_session.config)
        mock_generate_report.assert_called_once()
        assert mock_session.exitstatus == 1

    def test_pytest_sessionfinish_without_api_cov_report(self):
        """Test pytest_sessionfinish when --api-cov-report is disabled."""

        class SimpleSession:
            def __init__(self):
                self.config = Mock()
                self.config.getoption.return_value = False

        mock_session = SimpleSession()

        pytest_sessionfinish(mock_session)

        assert not hasattr(mock_session, "api_coverage_data")

    @patch("pytest_api_cov.config.get_pytest_api_cov_report_config")
    @patch("pytest_api_cov.report.generate_pytest_api_cov_report")
    def test_pytest_sessionfinish_with_workeroutput(self, mock_generate_report, mock_get_config):
        """Test pytest_sessionfinish with workeroutput (parallel execution)."""
        mock_session = Mock()
        mock_session.config.getoption.return_value = True

        coverage_data = SessionData()
        coverage_data.recorder.record_call("/test", "test_func")
        coverage_data.discovered_endpoints.endpoints = ["GET /test"]
        mock_session.api_coverage_data = coverage_data
        mock_session.exitstatus = 0

        workeroutput = {"api_call_recorder": {"GET /worker_test": ["worker_test"]}}
        mock_session.config.workeroutput = workeroutput

        mock_config = Mock()
        mock_get_config.return_value = mock_config
        mock_generate_report.return_value = 0

        pytest_sessionfinish(mock_session)

        assert workeroutput["api_call_recorder"] == {"GET /test": ["test_func"]}
        assert workeroutput["discovered_endpoints"] == ["GET /test"]

    @patch("pytest_api_cov.plugin.get_pytest_api_cov_report_config")
    @patch("pytest_api_cov.plugin.generate_pytest_api_cov_report")
    def test_pytest_sessionfinish_with_worker_data(self, mock_generate_report, mock_get_config):
        """Test pytest_sessionfinish with worker data merging."""
        mock_session = Mock()
        mock_session.config.getoption.side_effect = lambda flag: flag == "--api-cov-report"

        coverage_data = SessionData()
        coverage_data.recorder.record_call("/test", "test_func")
        coverage_data.discovered_endpoints.endpoints = ["GET /test"]
        mock_session.api_coverage_data = coverage_data
        mock_session.exitstatus = 0

        worker_data = {"/worker_test": ["worker_test"]}
        mock_session.config.worker_api_call_recorder = worker_data
        mock_session.config.worker_discovered_endpoints = ["GET /worker_test"]

        del mock_session.config.workeroutput

        mock_config = Mock()
        mock_get_config.return_value = mock_config
        mock_generate_report.return_value = 0

        pytest_sessionfinish(mock_session)

        mock_generate_report.assert_called_once()
        call_args = mock_generate_report.call_args
        called_data = call_args[1]["called_data"]
        assert "GET /test" in called_data
        assert "/worker_test" in called_data

    @patch("pytest_api_cov.plugin.get_pytest_api_cov_report_config")
    @patch("pytest_api_cov.plugin.generate_pytest_api_cov_report")
    def test_pytest_sessionfinish_with_non_dict_worker_data(self, mock_generate_report, mock_get_config):
        """Test pytest_sessionfinish with non-dict worker data."""
        mock_session = Mock()
        mock_session.config.getoption.side_effect = lambda flag: flag == "--api-cov-report"

        coverage_data = SessionData()
        coverage_data.recorder.record_call("/test", "test_func")
        coverage_data.discovered_endpoints.endpoints = ["/test"]
        mock_session.api_coverage_data = coverage_data
        mock_session.exitstatus = 0

        from collections import defaultdict

        class NonDictWorkerData:
            def __init__(self):
                self.data = defaultdict(set)

            def __getitem__(self, key):
                return self.data[key]

            def update(self, other):
                if hasattr(other, "items"):
                    for k, v in other.items():
                        self.data[k].update(v)

            def items(self):
                return self.data.items()

            def __iter__(self):
                return iter(self.data)

            def keys(self):
                return self.data.keys()

            def values(self):
                return self.data.values()

            def __bool__(self):
                return bool(self.data)

        mock_session.config.worker_api_call_recorder = NonDictWorkerData()
        mock_session.config.worker_discovered_endpoints = []

        del mock_session.config.workeroutput

        mock_config = Mock()
        mock_get_config.return_value = mock_config
        mock_generate_report.return_value = 0

        pytest_sessionfinish(mock_session)

        mock_generate_report.assert_called_once()

    def test_pytest_configure_with_xdist(self):
        """Test pytest_configure when pytest-xdist is available."""
        mock_config = Mock()
        mock_config.getoption.return_value = True  # --api-cov-report is enabled
        mock_config.option.verbose = 1  # -v verbosity level
        mock_config.pluginmanager.hasplugin.return_value = True

        pytest_configure(mock_config)

        # DeferXdistPlugin
        mock_config.pluginmanager.register.assert_called_once()

    def test_pytest_configure_without_xdist(self):
        """Test pytest_configure when pytest-xdist is not available."""
        mock_config = Mock()
        mock_config.getoption.return_value = True  # --api-cov-report is enabled
        mock_config.option.verbose = 0  # no verbosity
        mock_config.pluginmanager.hasplugin.return_value = False

        pytest_configure(mock_config)

        mock_config.pluginmanager.register.assert_not_called()

    def test_pytest_configure_without_api_cov_report(self):
        """Test pytest_configure when --api-cov-report is not enabled."""
        mock_config = Mock()
        mock_config.getoption.return_value = False  # --api-cov-report is not enabled
        mock_config.pluginmanager.hasplugin.return_value = True

        pytest_configure(mock_config)

        mock_config.pluginmanager.register.assert_called_once()

    @pytest.mark.parametrize(
        ("verbose_level", "expected_log_level"),
        [
            (0, "WARNING"),  # normal run
            (1, "INFO"),  # -v
            (2, "DEBUG"),  # -vv or more
            (3, "DEBUG"),  # -vvv
        ],
    )
    @patch("pytest_api_cov.plugin.logger")
    def test_pytest_configure_logging_levels(self, mock_logger, verbose_level, expected_log_level):
        """Test that logging levels are set correctly based on verbosity."""
        import logging

        mock_config = Mock()
        mock_config.getoption.return_value = True  # --api-cov-report enabled
        mock_config.option.verbose = verbose_level
        mock_config.pluginmanager.hasplugin.return_value = False
        mock_logger.handlers = []

        pytest_configure(mock_config)

        expected_level = getattr(logging, expected_log_level)
        mock_logger.setLevel.assert_called_with(expected_level)

    @patch("pytest_api_cov.plugin.logger")
    def test_pytest_configure_existing_handler(self, mock_logger):
        """Test that no new handler is added if one already exists."""
        mock_config = Mock()
        mock_config.getoption.return_value = True
        mock_config.option.verbose = 1
        mock_config.pluginmanager.hasplugin.return_value = False
        mock_logger.handlers = [Mock()]

        pytest_configure(mock_config)

        mock_logger.addHandler.assert_not_called()


class TestDeferXdistPlugin:
    """Tests for the DeferXdistPlugin class."""

    def test_pytest_testnodedown_with_worker_data(self):
        """Test pytest_testnodedown when worker data is available."""
        mock_node = Mock()
        mock_node.workeroutput = {"api_call_recorder": {"/test": ["test_func"]}}

        worker_data = defaultdict(set)
        mock_node.config.worker_api_call_recorder = worker_data

        plugin = DeferXdistPlugin()
        plugin.pytest_testnodedown(mock_node)

        assert "/test" in worker_data
        assert "test_func" in worker_data["/test"]

    def test_pytest_testnodedown_without_worker_data(self):
        """Test pytest_testnodedown when no worker data is available."""
        mock_node = Mock()
        mock_node.workeroutput = {}
        mock_node.config.worker_api_call_recorder = {}

        plugin = DeferXdistPlugin()
        plugin.pytest_testnodedown(mock_node)

        assert mock_node.config.worker_api_call_recorder == {}

    def test_pytest_testnodedown_with_existing_worker_data(self):
        """Test pytest_testnodedown when worker data already exists."""
        mock_node = Mock()
        mock_node.workeroutput = {"api_call_recorder": {"/new": ["new_test"]}}

        worker_data = defaultdict(set)
        worker_data["/existing"].add("existing_test")
        mock_node.config.worker_api_call_recorder = worker_data

        plugin = DeferXdistPlugin()
        plugin.pytest_testnodedown(mock_node)

        assert "/existing" in worker_data
        assert "/new" in worker_data
        assert "existing_test" in worker_data["/existing"]
        assert "new_test" in worker_data["/new"]


def test_extract_app_from_client_variants():
    """Extract app from different client shapes."""
    app = object()

    class A:
        def __init__(self):
            self.app = app

    class B:
        def __init__(self):
            self.application = app

    class Transport:
        def __init__(self):
            self.app = app

    class C:
        def __init__(self):
            self._transport = Transport()

    class D:
        def __init__(self):
            self._app = app

    assert extract_app_from_client(A()) is app
    assert extract_app_from_client(B()) is app
    assert extract_app_from_client(C()) is app
    assert extract_app_from_client(D()) is app
    assert extract_app_from_client(None) is None


def test_wrap_client_with_coverage_records_various_call_patterns():
    """Tracked client records calls for string path, request-like, and kwargs."""
    recorder = Mock()

    class DummyReq:
        def __init__(self, path, method="GET"):
            class URL:
                def __init__(self, p):
                    self.path = p

            self.url = URL(path)
            self.method = method

    class Client:
        def get(self, *args, **kwargs):
            return "GET-OK"

        def open(self, *args, **kwargs):
            return "OPEN-OK"

    client = Client()
    wrapped = wrap_client_with_coverage(client, recorder, "test_fn")

    assert wrapped.get("/foo") == "GET-OK"
    recorder.record_call.assert_called_with("/foo", "test_fn", "GET")

    recorder.reset_mock()

    req = DummyReq("/bar", method="POST")
    assert wrapped.get(req) == "GET-OK"
    recorder.record_call.assert_called_with("/bar", "test_fn", "POST")

    recorder.reset_mock()

    assert wrapped.open(path="/baz", method="PUT") == "OPEN-OK"
    recorder.record_call.assert_called_with("/baz", "test_fn", "PUT")


def test_create_coverage_fixture_returns_existing_client_when_coverage_disabled():
    """create_coverage_fixture yields existing fixture when coverage disabled."""
    fixture = create_coverage_fixture("my_client", existing_fixture_name="existing")

    class SimpleSession:
        def __init__(self):
            self.config = Mock()
            self.config.getoption.return_value = False

    session = SimpleSession()

    class Req:
        def __init__(self):
            self.node = Mock()
            self.node.session = session

        def getfixturevalue(self, name):
            if name == "existing":
                return "I-AM-EXISTING-CLIENT"
            raise pytest.FixtureLookupError(name)

    req = Req()
    raw_fixture = getattr(fixture, "__wrapped__", fixture)
    gen = raw_fixture(req)
    got = next(gen)
    assert got == "I-AM-EXISTING-CLIENT"
    with pytest.raises(StopIteration):
        next(gen)


@patch("pytest_api_cov.frameworks.get_framework_adapter")
def test_create_coverage_fixture_falls_back_to_app_when_no_existing_and_coverage_disabled(mock_get_adapter):
    """When no existing client but an app fixture exists and coverage disabled, create tracked client."""
    fixture = create_coverage_fixture("my_client", existing_fixture_name=None)

    class SimpleSession:
        def __init__(self):
            self.config = Mock()
            self.config.getoption.return_value = False

    session = SimpleSession()

    class Req:
        def __init__(self):
            self.node = Mock()
            self.node.session = session

        def getfixturevalue(self, name):
            if name == "app":
                return "APP-OBJ"
            raise pytest.FixtureLookupError(name)

    adapter = Mock()
    adapter.get_tracked_client.return_value = "CLIENT-FROM-APP"
    mock_get_adapter.return_value = adapter

    req = Req()
    # Unwrap pytest.fixture wrapper to call the inner generator directly
    raw_fixture = getattr(fixture, "__wrapped__", fixture)
    gen = raw_fixture(req)
    got = next(gen)
    assert got == "CLIENT-FROM-APP"
    mock_get_adapter.assert_called_once_with("APP-OBJ")
    with pytest.raises(StopIteration):
        next(gen)
