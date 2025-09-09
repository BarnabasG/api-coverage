"""Tests for the pytest plugin."""

from collections import defaultdict
from unittest.mock import Mock, patch

import pytest

from pytest_api_cov.models import SessionData
from pytest_api_cov.plugin import (
    DeferXdistPlugin,
    auto_discover_app,
    get_helpful_error_message,
    is_supported_framework,
    pytest_addoption,
    pytest_configure,
    pytest_sessionfinish,
    pytest_sessionstart,
)


class TestSupportedFramework:
    """Tests for framework detection utility functions."""

    def test_package_version(self):
        """Test that package version is accessible."""
        import pytest_api_cov

        assert hasattr(pytest_api_cov, "__version__")
        assert isinstance(pytest_api_cov.__version__, str)
        assert pytest_api_cov.__version__ == "1.0.0"

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

    @patch("os.path.exists", return_value=False)
    def test_auto_discover_app_no_files(self, mock_exists):
        """Test auto-discovery when no app files exist."""
        result = auto_discover_app()
        assert result is None

    @patch("os.path.exists", return_value=True)
    @patch("importlib.util.spec_from_file_location")
    @patch("importlib.util.module_from_spec")
    def test_auto_discover_app_import_error(self, mock_module_from_spec, mock_spec_from_file, mock_exists):
        """Test auto-discovery when import fails."""
        mock_spec_from_file.return_value = None
        result = auto_discover_app()
        assert result is None

    def test_get_helpful_error_message(self):
        """Test that helpful error message is generated."""
        message = get_helpful_error_message()
        assert "No API app found" in message
        assert "Quick Setup Options" in message
        assert "pytest-api-cov init" in message


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
        coverage_data.discovered_endpoints.endpoints = ["/test"]
        mock_session.api_coverage_data = coverage_data
        mock_session.exitstatus = 0

        workeroutput = {"api_call_recorder": {"/worker_test": ["worker_test"]}}
        mock_session.config.workeroutput = workeroutput

        mock_config = Mock()
        mock_get_config.return_value = mock_config
        mock_generate_report.return_value = 0

        pytest_sessionfinish(mock_session)

        assert workeroutput["api_call_recorder"] == {"/test": ["test_func"]}
        assert workeroutput["discovered_endpoints"] == ["/test"]

    @patch("pytest_api_cov.plugin.get_pytest_api_cov_report_config")
    @patch("pytest_api_cov.plugin.generate_pytest_api_cov_report")
    def test_pytest_sessionfinish_with_worker_data(self, mock_generate_report, mock_get_config):
        """Test pytest_sessionfinish with worker data merging."""
        mock_session = Mock()
        mock_session.config.getoption.side_effect = lambda flag: flag == "--api-cov-report"

        coverage_data = SessionData()
        coverage_data.recorder.record_call("/test", "test_func")
        coverage_data.discovered_endpoints.endpoints = ["/test"]
        mock_session.api_coverage_data = coverage_data
        mock_session.exitstatus = 0

        worker_data = {"/worker_test": ["worker_test"]}
        mock_session.config.worker_api_call_recorder = worker_data
        mock_session.config.worker_discovered_endpoints = ["/worker_test"]

        del mock_session.config.workeroutput

        mock_config = Mock()
        mock_get_config.return_value = mock_config
        mock_generate_report.return_value = 0

        pytest_sessionfinish(mock_session)

        mock_generate_report.assert_called_once()
        call_args = mock_generate_report.call_args
        called_data = call_args[1]["called_data"]
        assert "/test" in called_data
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
        "verbose_level,expected_log_level",
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
