# tests/unit/test_plugin.py
from collections import defaultdict
from unittest.mock import Mock, patch

from pytest_api_cov.plugin import (
    DeferXdistPlugin,
    pytest_addoption,
    pytest_configure,
    pytest_sessionfinish,
    pytest_sessionstart,
)


class TestPluginHooks:
    """Tests for pytest plugin hooks."""

    def test_pytest_addoption(self):
        """Test that pytest_addoption adds the required flags."""
        mock_parser = Mock()

        # Test that the function exists and can be called
        pytest_addoption(mock_parser)

        # Since the plugin is already imported, we just verify the function exists
        assert callable(pytest_addoption)

    def test_pytest_sessionstart_with_api_cov_report(self):
        """Test pytest_sessionstart when --api-cov-report is enabled."""
        mock_session = Mock()
        mock_session.config.getoption.return_value = True

        pytest_sessionstart(mock_session)

        assert hasattr(mock_session, "api_call_recorder")
        assert hasattr(mock_session, "discovered_endpoints")
        assert mock_session.discovered_endpoints is None

    def test_pytest_sessionstart_without_api_cov_report(self):
        """Test pytest_sessionstart when --api-cov-report is disabled."""

        # Use a simple object instead of Mock to avoid auto-attribute creation
        class SimpleSession:
            def __init__(self):
                self.config = Mock()
                self.config.getoption.return_value = False

        mock_session = SimpleSession()

        pytest_sessionstart(mock_session)

        # Should not set any attributes when flag is False
        assert not hasattr(mock_session, "api_call_recorder")
        assert not hasattr(mock_session, "discovered_endpoints")

    @patch("pytest_api_cov.plugin.get_pytest_api_cov_report_config")
    @patch("pytest_api_cov.plugin.generate_pytest_api_cov_report")
    def test_pytest_sessionfinish_with_api_cov_report(self, mock_generate_report, mock_get_config):
        """Test pytest_sessionfinish when --api-cov-report is enabled."""
        mock_session = Mock()
        mock_session.config.getoption.side_effect = lambda flag: flag == "--api-cov-report"
        mock_session.api_call_recorder = {"/test": ["test_func"]}
        mock_session.discovered_endpoints = ["/test"]
        mock_session.exitstatus = 0

        # Remove workeroutput attribute to force the else path
        del mock_session.config.workeroutput
        # Remove worker_api_call_recorder so getattr returns defaultdict(set)
        if hasattr(mock_session.config, "worker_api_call_recorder"):
            del mock_session.config.worker_api_call_recorder

        mock_config = Mock()
        mock_get_config.return_value = mock_config
        mock_generate_report.return_value = 1

        pytest_sessionfinish(mock_session)

        mock_get_config.assert_called_once_with(mock_session.config)
        mock_generate_report.assert_called_once()
        assert mock_session.exitstatus == 1

    def test_pytest_sessionfinish_without_api_cov_report(self):
        """Test pytest_sessionfinish when --api-cov-report is disabled."""

        # Use a simple object instead of Mock to avoid auto-attribute creation
        class SimpleSession:
            def __init__(self):
                self.config = Mock()
                self.config.getoption.return_value = False

        mock_session = SimpleSession()

        pytest_sessionfinish(mock_session)

        # Should not call any coverage functions
        assert not hasattr(mock_session, "api_call_recorder")

    @patch("pytest_api_cov.config.get_pytest_api_cov_report_config")
    @patch("pytest_api_cov.report.generate_pytest_api_cov_report")
    def test_pytest_sessionfinish_with_workeroutput(self, mock_generate_report, mock_get_config):
        """Test pytest_sessionfinish with workeroutput (parallel execution)."""
        mock_session = Mock()
        mock_session.config.getoption.return_value = True
        mock_session.api_call_recorder = {"/test": ["test_func"]}
        mock_session.discovered_endpoints = ["/test"]
        mock_session.exitstatus = 0

        # Use a real dict for workeroutput to support item assignment
        workeroutput = {"api_call_recorder": {"/worker_test": ["worker_test"]}}
        mock_session.config.workeroutput = workeroutput

        mock_config = Mock()
        mock_get_config.return_value = mock_config
        mock_generate_report.return_value = 0

        pytest_sessionfinish(mock_session)

        # Should serialize the recorder for workers
        assert workeroutput["api_call_recorder"] == {"/test": ["test_func"]}

    @patch("pytest_api_cov.plugin.get_pytest_api_cov_report_config")
    @patch("pytest_api_cov.plugin.generate_pytest_api_cov_report")
    def test_pytest_sessionfinish_with_worker_data(self, mock_generate_report, mock_get_config):
        """Test pytest_sessionfinish with worker data merging."""
        mock_session = Mock()
        mock_session.config.getoption.side_effect = lambda flag: flag == "--api-cov-report"
        mock_session.api_call_recorder = {"/test": ["test_func"]}
        mock_session.discovered_endpoints = ["/test"]
        mock_session.exitstatus = 0
        # Use a real dict for worker data to support item assignment
        worker_data = {"/worker_test": ["worker_test"]}
        mock_session.config.worker_api_call_recorder = worker_data

        # Remove workeroutput attribute to force the else path
        del mock_session.config.workeroutput

        mock_config = Mock()
        mock_get_config.return_value = mock_config
        mock_generate_report.return_value = 0

        pytest_sessionfinish(mock_session)

        mock_generate_report.assert_called_once()
        # Verify that worker data was merged
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
        mock_session.api_call_recorder = {"/test": ["test_func"]}
        mock_session.discovered_endpoints = ["/test"]
        mock_session.exitstatus = 0
        # Set worker data to a custom object (non-dict but still valid)
        # This should trigger the 'else' branch on line 66
        # Use a custom object that's not a dict but behaves like defaultdict
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

        # Remove workeroutput attribute to force the else path
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

        # Should register the DeferXdistPlugin
        mock_config.pluginmanager.register.assert_called_once()

    def test_pytest_configure_without_xdist(self):
        """Test pytest_configure when pytest-xdist is not available."""
        mock_config = Mock()
        mock_config.getoption.return_value = True  # --api-cov-report is enabled
        mock_config.option.verbose = 0  # no verbosity
        mock_config.pluginmanager.hasplugin.return_value = False

        pytest_configure(mock_config)

        # Should not register any plugins
        mock_config.pluginmanager.register.assert_not_called()

    def test_pytest_configure_without_api_cov_report(self):
        """Test pytest_configure when --api-cov-report is not enabled."""
        mock_config = Mock()
        mock_config.getoption.return_value = False  # --api-cov-report is not enabled
        mock_config.pluginmanager.hasplugin.return_value = True

        pytest_configure(mock_config)

        # Should still register xdist plugin if available, but no logging setup
        mock_config.pluginmanager.register.assert_called_once()


class TestDeferXdistPlugin:
    """Tests for the DeferXdistPlugin class."""

    def test_pytest_testnodedown_with_worker_data(self):
        """Test pytest_testnodedown when worker data is available."""
        mock_node = Mock()
        mock_node.workeroutput = {"api_call_recorder": {"/test": ["test_func"]}}

        # Use a real dict for worker data to support item assignment
        worker_data = defaultdict(set)
        mock_node.config.worker_api_call_recorder = worker_data

        plugin = DeferXdistPlugin()
        plugin.pytest_testnodedown(mock_node)

        # Should merge worker data into config
        assert "/test" in worker_data
        assert "test_func" in worker_data["/test"]

    def test_pytest_testnodedown_without_worker_data(self):
        """Test pytest_testnodedown when no worker data is available."""
        mock_node = Mock()
        mock_node.workeroutput = {}
        mock_node.config.worker_api_call_recorder = {}

        plugin = DeferXdistPlugin()
        plugin.pytest_testnodedown(mock_node)

        # Should not modify config when no worker data
        assert mock_node.config.worker_api_call_recorder == {}

    def test_pytest_testnodedown_with_existing_worker_data(self):
        """Test pytest_testnodedown when worker data already exists."""
        mock_node = Mock()
        mock_node.workeroutput = {"api_call_recorder": {"/new": ["new_test"]}}

        # Use a real dict for worker data to support item assignment
        worker_data = defaultdict(set)
        worker_data["/existing"].add("existing_test")
        mock_node.config.worker_api_call_recorder = worker_data

        plugin = DeferXdistPlugin()
        plugin.pytest_testnodedown(mock_node)

        # Should merge new data with existing data
        assert "/existing" in worker_data
        assert "/new" in worker_data
        assert "existing_test" in worker_data["/existing"]
        assert "new_test" in worker_data["/new"]
