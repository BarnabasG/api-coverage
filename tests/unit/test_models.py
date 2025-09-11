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

        assert "GET /test" in recorder
        assert "test_func" in recorder.get_callers("GET /test")
        assert len(recorder) == 1

    def test_record_call_with_method(self):
        """Test recording a call with specific HTTP method."""
        recorder = ApiCallRecorder()
        recorder.record_call("/test", "test_func", "POST")

        assert "POST /test" in recorder
        assert "test_func" in recorder.get_callers("POST /test")
        assert len(recorder) == 1

    def test_record_call_different_methods_same_endpoint(self):
        """Test recording calls to same endpoint with different methods."""
        recorder = ApiCallRecorder()
        recorder.record_call("/test", "test_get", "GET")
        recorder.record_call("/test", "test_post", "POST")

        assert "GET /test" in recorder
        assert "POST /test" in recorder
        assert "test_get" in recorder.get_callers("GET /test")
        assert "test_post" in recorder.get_callers("POST /test")
        assert len(recorder) == 2

    def test_get_called_methods_for_endpoint(self):
        """Test getting all methods called for a specific endpoint."""
        recorder = ApiCallRecorder()
        recorder.record_call("/users", "test1", "GET")
        recorder.record_call("/users", "test2", "POST")
        recorder.record_call("/items", "test3", "GET")

        methods = recorder.get_called_methods_for_endpoint("/users")
        assert sorted(methods) == ["GET", "POST"]

        methods = recorder.get_called_methods_for_endpoint("/items")
        assert methods == ["GET"]

    def test_get_called_endpoints_for_method(self):
        """Test getting all endpoints called with a specific method."""
        recorder = ApiCallRecorder()
        recorder.record_call("/users", "test1", "GET")
        recorder.record_call("/items", "test2", "GET")
        recorder.record_call("/users", "test3", "POST")

        endpoints = recorder.get_called_endpoints_for_method("GET")
        assert sorted(endpoints) == ["/items", "/users"]

        endpoints = recorder.get_called_endpoints_for_method("POST")
        assert endpoints == ["/users"]

    def test_record_call_existing_endpoint(self):
        """Test recording additional calls to existing endpoint."""
        recorder = ApiCallRecorder()
        recorder.record_call("/test", "test_func1")
        recorder.record_call("/test", "test_func2")

        callers = recorder.get_callers("GET /test")
        assert "test_func1" in callers
        assert "test_func2" in callers
        assert len(callers) == 2

    def test_record_call_duplicate(self):
        """Test recording duplicate calls (should not create duplicates)."""
        recorder = ApiCallRecorder()
        recorder.record_call("/test", "test_func")
        recorder.record_call("/test", "test_func")

        callers = recorder.get_callers("GET /test")
        assert len(callers) == 1
        assert "test_func" in callers

    def test_get_called_endpoints(self):
        """Test getting list of called endpoints."""
        recorder = ApiCallRecorder()
        recorder.record_call("/endpoint1", "test1")
        recorder.record_call("/endpoint2", "test2")

        endpoints = recorder.get_called_endpoints()
        assert len(endpoints) == 2
        assert "GET /endpoint1" in endpoints
        assert "GET /endpoint2" in endpoints

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
        assert "test1" in recorder1.get_callers("GET /test")

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
        assert "test1" in recorder1.get_callers("GET /endpoint1")
        assert "test2" in recorder1.get_callers("GET /endpoint2")

        shared_callers = recorder1.get_callers("GET /shared")
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
        assert isinstance(serializable["GET /test1"], list)
        assert isinstance(serializable["GET /test2"], list)
        assert set(serializable["GET /test1"]) == {"func1", "func2"}
        assert serializable["GET /test2"] == ["func3"]

    def test_from_serializable(self):
        """Test creating from serializable format."""
        data = {"GET /test1": ["func1", "func2"], "POST /test2": ["func3"]}

        recorder = ApiCallRecorder.from_serializable(data)

        assert len(recorder) == 2
        assert "GET /test1" in recorder
        assert "POST /test2" in recorder
        assert recorder.get_callers("GET /test1") == {"func1", "func2"}
        assert recorder.get_callers("POST /test2") == {"func3"}

    def test_contains(self):
        """Test __contains__ method."""
        recorder = ApiCallRecorder()
        recorder.record_call("/test", "func")

        assert "GET /test" in recorder
        assert "POST /test" not in recorder
        assert "GET /nonexistent" not in recorder

    def test_items(self):
        """Test items() method."""
        recorder = ApiCallRecorder()
        recorder.record_call("/test1", "func1")
        recorder.record_call("/test2", "func2")

        items = list(recorder.items())
        assert len(items) == 2

        endpoints = [item[0] for item in items]
        assert "GET /test1" in endpoints
        assert "GET /test2" in endpoints

    def test_keys(self):
        """Test keys() method."""
        recorder = ApiCallRecorder()
        recorder.record_call("/test1", "func1")
        recorder.record_call("/test2", "func2")

        keys = list(recorder.keys())
        assert len(keys) == 2
        assert "GET /test1" in keys
        assert "GET /test2" in keys

    def test_values(self):
        """Test values() method."""
        recorder = ApiCallRecorder()
        recorder.record_call("/test1", "func1")
        recorder.record_call("/test2", "func2")

        values = list(recorder.values())
        assert len(values) == 2

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
        endpoints = ["GET /test1", "POST /test2"]
        discovery = EndpointDiscovery(endpoints=endpoints, discovery_source="test")

        assert discovery.endpoints == endpoints
        assert discovery.discovery_source == "test"
        assert len(discovery) == 2

    def test_add_endpoint_new(self):
        """Test adding a new endpoint."""
        discovery = EndpointDiscovery()
        discovery.add_endpoint("/test")

        assert len(discovery) == 1
        assert "GET /test" in discovery.endpoints

    def test_add_endpoint_with_method(self):
        """Test adding an endpoint with specific method."""
        discovery = EndpointDiscovery()
        discovery.add_endpoint("/test", "POST")

        assert len(discovery) == 1
        assert "POST /test" in discovery.endpoints

    def test_add_endpoint_duplicate(self):
        """Test adding duplicate endpoint (should not create duplicates)."""
        discovery = EndpointDiscovery()
        discovery.add_endpoint("/test")
        discovery.add_endpoint("/test")

        assert len(discovery) == 1
        assert discovery.endpoints.count("GET /test") == 1

    def test_merge_empty(self):
        """Test merging with empty discovery."""
        discovery1 = EndpointDiscovery()
        discovery1.add_endpoint("/test1")

        discovery2 = EndpointDiscovery()

        discovery1.merge(discovery2)
        assert len(discovery1) == 1
        assert "GET /test1" in discovery1.endpoints

    def test_merge_with_data(self):
        """Test merging with another discovery containing data."""
        discovery1 = EndpointDiscovery()
        discovery1.add_endpoint("/test1")
        discovery1.add_endpoint("/shared")

        discovery2 = EndpointDiscovery()
        discovery2.add_endpoint("/test2")
        discovery2.add_endpoint("/shared")

        discovery1.merge(discovery2)

        assert len(discovery1) == 3
        assert "GET /test1" in discovery1.endpoints
        assert "GET /test2" in discovery1.endpoints
        assert discovery1.endpoints.count("GET /shared") == 1

    def test_iter(self):
        """Test __iter__ method."""
        discovery = EndpointDiscovery()
        discovery.add_endpoint("/test1")
        discovery.add_endpoint("/test2")

        endpoints = list(discovery)
        assert len(endpoints) == 2
        assert "GET /test1" in endpoints
        assert "GET /test2" in endpoints


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

        assert "GET /test" in session.recorder
        assert "test_func" in session.recorder.get_callers("GET /test")

    def test_record_call_with_method(self):
        """Test record_call with specific method."""
        session = SessionData()
        session.record_call("/test", "test_func", "POST")

        assert "POST /test" in session.recorder
        assert "test_func" in session.recorder.get_callers("POST /test")

    def test_add_discovered_endpoint(self):
        """Test add_discovered_endpoint convenience method."""
        session = SessionData()
        session.add_discovered_endpoint("/test", "GET", "flask_adapter")

        assert "GET /test" in session.discovered_endpoints.endpoints
        assert session.discovered_endpoints.discovery_source == "flask_adapter"

    def test_add_discovered_endpoint_multiple(self):
        """Test adding multiple discovered endpoints."""
        session = SessionData()
        session.add_discovered_endpoint("/test1", "GET", "flask_adapter")
        session.add_discovered_endpoint("/test2", "POST", "flask_adapter")

        assert len(session.discovered_endpoints) == 2
        assert "GET /test1" in session.discovered_endpoints.endpoints
        assert "POST /test2" in session.discovered_endpoints.endpoints
        assert session.discovered_endpoints.discovery_source == "flask_adapter"

    def test_merge_worker_data_dict_serializable(self):
        """Test merging worker data in serializable format."""
        session = SessionData()
        session.record_call("/session", "session_test")

        worker_recorder = {"GET /worker": ["worker_test"]}
        worker_endpoints = ["POST /worker_endpoint"]

        session.merge_worker_data(worker_recorder, worker_endpoints)

        assert "GET /session" in session.recorder
        assert "GET /worker" in session.recorder
        assert "session_test" in session.recorder.get_callers("GET /session")
        assert "worker_test" in session.recorder.get_callers("GET /worker")

        assert "POST /worker_endpoint" in session.discovered_endpoints.endpoints

    def test_merge_worker_data_dict_raw(self):
        """Test merging worker data in raw dict format."""
        session = SessionData()
        session.record_call("/session", "session_test")

        worker_recorder = {"/worker": {"worker_test"}}
        worker_endpoints = ["/worker_endpoint"]

        session.merge_worker_data(worker_recorder, worker_endpoints)

        assert "/worker" in session.recorder
        assert "worker_test" in session.recorder.get_callers("/worker")

    def test_merge_worker_data_dict_mixed(self):
        """Test merging worker data with mixed types."""
        session = SessionData()

        worker_recorder = {
            "/list": ["test1", "test2"],
            "/set": {"test3"},
            "/string": "test4",
        }
        worker_endpoints = []

        session.merge_worker_data(worker_recorder, worker_endpoints)

        assert "test1" in session.recorder.get_callers("/list")
        assert "test2" in session.recorder.get_callers("/list")
        assert "test3" in session.recorder.get_callers("/set")
        assert "test4" in session.recorder.get_callers("/string")

    @pytest.mark.parametrize(
        "worker_recorder,worker_endpoints,expected_recorder_len,expected_endpoints",
        [
            ({}, ["GET /worker_endpoint"], 1, ["GET /worker_endpoint"]),
            ({"GET /worker": ["worker_test"]}, [], 1, []),
            ("not_a_dict", ["POST /worker_endpoint"], 0, ["POST /worker_endpoint"]),
            (None, ["PUT /worker_endpoint"], 0, ["PUT /worker_endpoint"]),
        ],
    )
    def test_merge_worker_data_edge_cases(
        self, worker_recorder, worker_endpoints, expected_recorder_len, expected_endpoints
    ):
        """Test merging worker data with various edge cases."""
        session = SessionData()
        if expected_recorder_len > 0:
            session.record_call("/session", "session_test")

        session.merge_worker_data(worker_recorder, worker_endpoints)

        if "GET /worker" in str(worker_recorder):
            assert "GET /worker" in session.recorder

        for endpoint in expected_endpoints:
            assert endpoint in session.discovered_endpoints.endpoints

    def test_add_discovered_endpoint_first_endpoint(self):
        """Test adding the first endpoint sets the discovery source."""
        session = SessionData()
        session.add_discovered_endpoint("/first", "flask_adapter")

        assert session.discovered_endpoints.discovery_source == "flask_adapter"
        assert "GET /first" in session.discovered_endpoints.endpoints

    def test_add_discovered_endpoint_subsequent_endpoints(self):
        """Test adding subsequent endpoints doesn't change the discovery source."""
        session = SessionData()
        session.add_discovered_endpoint("/first", "flask_adapter")
        session.add_discovered_endpoint("/second", "fastapi_adapter")

        assert session.discovered_endpoints.discovery_source == "flask_adapter"
        assert "GET /first" in session.discovered_endpoints.endpoints
        assert "GET /second" in session.discovered_endpoints.endpoints
