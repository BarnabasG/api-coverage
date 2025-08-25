"""Unit tests for pytest-api-cov models."""

import pytest
from pytest_api_cov.models import ApiCallRecorder, EndpointDiscovery, SessionData


class TestApiCallRecorder:
    """Tests for ApiCallRecorder model."""

    def test_init_default(self):
        """Test ApiCallRecorder initialization with defaults."""
        recorder = ApiCallRecorder()
        assert recorder.calls == {}
        assert len(recorder) == 0

    def test_record_call_new_endpoint(self):
        """Test recording a call to a new endpoint."""
        recorder = ApiCallRecorder()
        recorder.record_call("/test", "test_func")
        
        assert "/test" in recorder
        assert "test_func" in recorder.get_callers("/test")
        assert len(recorder) == 1

    def test_record_call_existing_endpoint(self):
        """Test recording additional calls to existing endpoint."""
        recorder = ApiCallRecorder()
        recorder.record_call("/test", "test_func1")
        recorder.record_call("/test", "test_func2")
        
        callers = recorder.get_callers("/test")
        assert "test_func1" in callers
        assert "test_func2" in callers
        assert len(callers) == 2

    def test_record_call_duplicate(self):
        """Test recording duplicate calls (should not create duplicates)."""
        recorder = ApiCallRecorder()
        recorder.record_call("/test", "test_func")
        recorder.record_call("/test", "test_func")  # Duplicate
        
        callers = recorder.get_callers("/test")
        assert len(callers) == 1
        assert "test_func" in callers

    def test_get_called_endpoints(self):
        """Test getting list of called endpoints."""
        recorder = ApiCallRecorder()
        recorder.record_call("/endpoint1", "test1")
        recorder.record_call("/endpoint2", "test2")
        
        endpoints = recorder.get_called_endpoints()
        assert len(endpoints) == 2
        assert "/endpoint1" in endpoints
        assert "/endpoint2" in endpoints

    def test_get_callers_nonexistent(self):
        """Test getting callers for non-existent endpoint."""
        recorder = ApiCallRecorder()
        callers = recorder.get_callers("/nonexistent")
        assert callers == set()

    def test_merge_empty_recorder(self):
        """Test merging with an empty recorder."""
        recorder1 = ApiCallRecorder()
        recorder1.record_call("/test", "test1")
        
        recorder2 = ApiCallRecorder()
        
        recorder1.merge(recorder2)
        assert len(recorder1) == 1
        assert "test1" in recorder1.get_callers("/test")

    def test_merge_with_data(self):
        """Test merging two recorders with data."""
        recorder1 = ApiCallRecorder()
        recorder1.record_call("/endpoint1", "test1")
        recorder1.record_call("/shared", "test1")
        
        recorder2 = ApiCallRecorder()
        recorder2.record_call("/endpoint2", "test2")
        recorder2.record_call("/shared", "test2")
        
        recorder1.merge(recorder2)
        
        assert len(recorder1) == 3
        assert "test1" in recorder1.get_callers("/endpoint1")
        assert "test2" in recorder1.get_callers("/endpoint2")
        
        shared_callers = recorder1.get_callers("/shared")
        assert "test1" in shared_callers
        assert "test2" in shared_callers
        assert len(shared_callers) == 2

    def test_to_serializable(self):
        """Test converting to serializable format."""
        recorder = ApiCallRecorder()
        recorder.record_call("/test1", "func1")
        recorder.record_call("/test1", "func2")
        recorder.record_call("/test2", "func3")
        
        serializable = recorder.to_serializable()
        
        assert isinstance(serializable, dict)
        assert len(serializable) == 2
        assert isinstance(serializable["/test1"], list)
        assert isinstance(serializable["/test2"], list)
        assert set(serializable["/test1"]) == {"func1", "func2"}
        assert serializable["/test2"] == ["func3"]

    def test_from_serializable(self):
        """Test creating from serializable format."""
        data = {
            "/test1": ["func1", "func2"],
            "/test2": ["func3"]
        }
        
        recorder = ApiCallRecorder.from_serializable(data)
        
        assert len(recorder) == 2
        assert "/test1" in recorder
        assert "/test2" in recorder
        assert recorder.get_callers("/test1") == {"func1", "func2"}
        assert recorder.get_callers("/test2") == {"func3"}

    def test_contains(self):
        """Test __contains__ method."""
        recorder = ApiCallRecorder()
        recorder.record_call("/test", "func")
        
        assert "/test" in recorder
        assert "/nonexistent" not in recorder

    def test_items(self):
        """Test items() method."""
        recorder = ApiCallRecorder()
        recorder.record_call("/test1", "func1")
        recorder.record_call("/test2", "func2")
        
        items = list(recorder.items())
        assert len(items) == 2
        
        # Check that items returns tuples of (endpoint, callers_set)
        endpoints = [item[0] for item in items]
        assert "/test1" in endpoints
        assert "/test2" in endpoints

    def test_keys(self):
        """Test keys() method."""
        recorder = ApiCallRecorder()
        recorder.record_call("/test1", "func1")
        recorder.record_call("/test2", "func2")
        
        keys = list(recorder.keys())
        assert len(keys) == 2
        assert "/test1" in keys
        assert "/test2" in keys

    def test_values(self):
        """Test values() method."""
        recorder = ApiCallRecorder()
        recorder.record_call("/test1", "func1")
        recorder.record_call("/test2", "func2")
        
        values = list(recorder.values())
        assert len(values) == 2
        
        # Check that all values are sets
        for value in values:
            assert isinstance(value, set)


class TestEndpointDiscovery:
    """Tests for EndpointDiscovery model."""

    def test_init_default(self):
        """Test EndpointDiscovery initialization with defaults."""
        discovery = EndpointDiscovery()
        assert discovery.endpoints == []
        assert discovery.discovery_source == "unknown"
        assert len(discovery) == 0

    def test_init_with_data(self):
        """Test EndpointDiscovery initialization with data."""
        endpoints = ["/test1", "/test2"]
        discovery = EndpointDiscovery(endpoints=endpoints, discovery_source="test")
        
        assert discovery.endpoints == endpoints
        assert discovery.discovery_source == "test"
        assert len(discovery) == 2

    def test_add_endpoint_new(self):
        """Test adding a new endpoint."""
        discovery = EndpointDiscovery()
        discovery.add_endpoint("/test")
        
        assert len(discovery) == 1
        assert "/test" in discovery.endpoints

    def test_add_endpoint_duplicate(self):
        """Test adding duplicate endpoint (should not create duplicates)."""
        discovery = EndpointDiscovery()
        discovery.add_endpoint("/test")
        discovery.add_endpoint("/test")  # Duplicate
        
        assert len(discovery) == 1
        assert discovery.endpoints.count("/test") == 1

    def test_merge_empty(self):
        """Test merging with empty discovery."""
        discovery1 = EndpointDiscovery()
        discovery1.add_endpoint("/test1")
        
        discovery2 = EndpointDiscovery()
        
        discovery1.merge(discovery2)
        assert len(discovery1) == 1
        assert "/test1" in discovery1.endpoints

    def test_merge_with_data(self):
        """Test merging with another discovery containing data."""
        discovery1 = EndpointDiscovery()
        discovery1.add_endpoint("/test1")
        discovery1.add_endpoint("/shared")
        
        discovery2 = EndpointDiscovery()
        discovery2.add_endpoint("/test2")
        discovery2.add_endpoint("/shared")  # Duplicate
        
        discovery1.merge(discovery2)
        
        assert len(discovery1) == 3  # Should not have duplicates
        assert "/test1" in discovery1.endpoints
        assert "/test2" in discovery1.endpoints
        assert discovery1.endpoints.count("/shared") == 1

    def test_iter(self):
        """Test __iter__ method."""
        discovery = EndpointDiscovery()
        discovery.add_endpoint("/test1")
        discovery.add_endpoint("/test2")
        
        endpoints = list(discovery)
        assert len(endpoints) == 2
        assert "/test1" in endpoints
        assert "/test2" in endpoints


class TestSessionData:
    """Tests for SessionData model."""

    def test_init_default(self):
        """Test SessionData initialization with defaults."""
        session = SessionData()
        
        assert isinstance(session.recorder, ApiCallRecorder)
        assert isinstance(session.discovered_endpoints, EndpointDiscovery)
        assert len(session.recorder) == 0
        assert len(session.discovered_endpoints) == 0

    def test_record_call(self):
        """Test record_call convenience method."""
        session = SessionData()
        session.record_call("/test", "test_func")
        
        assert "/test" in session.recorder
        assert "test_func" in session.recorder.get_callers("/test")

    def test_add_discovered_endpoint(self):
        """Test add_discovered_endpoint convenience method."""
        session = SessionData()
        session.add_discovered_endpoint("/test", "flask_adapter")
        
        assert "/test" in session.discovered_endpoints.endpoints
        assert session.discovered_endpoints.discovery_source == "flask_adapter"

    def test_add_discovered_endpoint_multiple(self):
        """Test adding multiple discovered endpoints."""
        session = SessionData()
        session.add_discovered_endpoint("/test1", "flask_adapter")
        session.add_discovered_endpoint("/test2", "flask_adapter")
        
        assert len(session.discovered_endpoints) == 2
        assert "/test1" in session.discovered_endpoints.endpoints
        assert "/test2" in session.discovered_endpoints.endpoints
        # Source should remain the same from first call
        assert session.discovered_endpoints.discovery_source == "flask_adapter"

    def test_merge_worker_data_dict_serializable(self):
        """Test merging worker data in serializable format."""
        session = SessionData()
        session.record_call("/session", "session_test")
        
        # Worker data in serializable format (lists)
        worker_recorder = {"/worker": ["worker_test"]}
        worker_endpoints = ["/worker_endpoint"]
        
        session.merge_worker_data(worker_recorder, worker_endpoints)
        
        # Check recorder merged
        assert "/session" in session.recorder
        assert "/worker" in session.recorder
        assert "session_test" in session.recorder.get_callers("/session")
        assert "worker_test" in session.recorder.get_callers("/worker")
        
        # Check endpoints merged
        assert "/worker_endpoint" in session.discovered_endpoints.endpoints

    def test_merge_worker_data_dict_raw(self):
        """Test merging worker data in raw dict format."""
        session = SessionData()
        session.record_call("/session", "session_test")
        
        # Worker data in raw format (not lists)
        worker_recorder = {"/worker": {"worker_test"}}  # Set instead of list
        worker_endpoints = ["/worker_endpoint"]
        
        session.merge_worker_data(worker_recorder, worker_endpoints)
        
        # Check recorder merged
        assert "/worker" in session.recorder
        assert "worker_test" in session.recorder.get_callers("/worker")

    def test_merge_worker_data_dict_mixed(self):
        """Test merging worker data with mixed types."""
        session = SessionData()
        
        # Worker data with mixed types
        worker_recorder = {
            "/list": ["test1", "test2"],  # List
            "/set": {"test3"},            # Set
            "/string": "test4"            # String (edge case - wrapped in set)
        }
        worker_endpoints = []
        
        session.merge_worker_data(worker_recorder, worker_endpoints)
        
        # Check all types are handled
        assert "test1" in session.recorder.get_callers("/list")
        assert "test2" in session.recorder.get_callers("/list")
        assert "test3" in session.recorder.get_callers("/set")
        # String is wrapped in {v}, so it becomes a set with the string as single element
        assert "test4" in session.recorder.get_callers("/string")

    @pytest.mark.parametrize("worker_recorder,worker_endpoints,expected_recorder_len,expected_endpoints", [
        ({}, ["/worker_endpoint"], 1, ["/worker_endpoint"]),  # Empty recorder
        ({"/worker": ["worker_test"]}, [], 1, []),            # Empty endpoints  
        ("not_a_dict", ["/worker_endpoint"], 0, ["/worker_endpoint"]),  # Non-dict recorder
        (None, ["/worker_endpoint"], 0, ["/worker_endpoint"]),          # Falsy recorder
    ])
    def test_merge_worker_data_edge_cases(self, worker_recorder, worker_endpoints, expected_recorder_len, expected_endpoints):
        """Test merging worker data with various edge cases."""
        session = SessionData()
        if expected_recorder_len > 0:
            session.record_call("/session", "session_test")
        
        session.merge_worker_data(worker_recorder, worker_endpoints)
        
        # Check recorder state
        if "/worker" in str(worker_recorder):
            assert "/worker" in session.recorder
        
        # Check endpoints state
        for endpoint in expected_endpoints:
            assert endpoint in session.discovered_endpoints.endpoints

    def test_add_discovered_endpoint_first_endpoint(self):
        """Test adding the first endpoint sets the discovery source."""
        session = SessionData()
        session.add_discovered_endpoint("/first", "flask_adapter")
        
        assert session.discovered_endpoints.discovery_source == "flask_adapter"
        assert "/first" in session.discovered_endpoints.endpoints

    def test_add_discovered_endpoint_subsequent_endpoints(self):
        """Test adding subsequent endpoints doesn't change the discovery source."""
        session = SessionData()
        session.add_discovered_endpoint("/first", "flask_adapter")
        session.add_discovered_endpoint("/second", "fastapi_adapter")
        
        # Source should remain from first endpoint
        assert session.discovered_endpoints.discovery_source == "flask_adapter"
        assert "/first" in session.discovered_endpoints.endpoints
        assert "/second" in session.discovered_endpoints.endpoints
