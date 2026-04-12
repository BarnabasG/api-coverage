"""Unit tests for pytest-api-cov models."""

import pytest

from pytest_api_cov.models import ApiCallRecorder, EndpointDiscovery, SessionData


class TestApiCallRecorder:
    """Tests for ApiCallRecorder."""

    def test_init_default(self):
        """Default init has empty calls."""
        recorder = ApiCallRecorder()
        assert recorder.calls == {}
        assert len(recorder) == 0

    def test_record_call_new_endpoint(self):
        """Record a call to a new endpoint."""
        recorder = ApiCallRecorder()
        recorder.record_call("/test", "test_func")

        assert "GET /test" in recorder
        assert "test_func" in recorder.calls["GET /test"]
        assert len(recorder) == 1

    def test_record_call_with_method(self):
        """Record a call with a specific HTTP method."""
        recorder = ApiCallRecorder()
        recorder.record_call("/test", "test_func", "POST")

        assert "POST /test" in recorder
        assert "test_func" in recorder.calls["POST /test"]
        assert len(recorder) == 1

    def test_record_call_different_methods_same_endpoint(self):
        """Same path with different methods creates separate entries."""
        recorder = ApiCallRecorder()
        recorder.record_call("/test", "test_get", "GET")
        recorder.record_call("/test", "test_post", "POST")

        assert "GET /test" in recorder
        assert "POST /test" in recorder
        assert "test_get" in recorder.calls["GET /test"]
        assert "test_post" in recorder.calls["POST /test"]
        assert len(recorder) == 2

    def test_record_call_existing_endpoint(self):
        """Multiple calls to the same endpoint accumulate callers."""
        recorder = ApiCallRecorder()
        recorder.record_call("/test", "test_func1")
        recorder.record_call("/test", "test_func2")

        callers = recorder.calls["GET /test"]
        assert "test_func1" in callers
        assert "test_func2" in callers
        assert len(callers) == 2

    def test_record_call_duplicate(self):
        """Duplicate calls are deduplicated (set behavior)."""
        recorder = ApiCallRecorder()
        recorder.record_call("/test", "test_func")
        recorder.record_call("/test", "test_func")

        callers = recorder.calls["GET /test"]
        assert len(callers) == 1
        assert "test_func" in callers

    def test_calls_keys(self):
        """Recorded endpoint keys are accessible."""
        recorder = ApiCallRecorder()
        recorder.record_call("/endpoint1", "test1")
        recorder.record_call("/endpoint2", "test2")

        endpoints = list(recorder.calls.keys())
        assert len(endpoints) == 2
        assert "GET /endpoint1" in endpoints
        assert "GET /endpoint2" in endpoints

    def test_calls_nonexistent(self):
        """Non-existent endpoint returns empty set via .get()."""
        recorder = ApiCallRecorder()
        callers = recorder.calls.get("GET /nonexistent", set())
        assert callers == set()

    def test_merge_empty_recorder(self):
        """Merging an empty recorder changes nothing."""
        recorder1 = ApiCallRecorder()
        recorder1.record_call("/test", "test1")

        recorder2 = ApiCallRecorder()

        recorder1.merge(recorder2)
        assert len(recorder1) == 1
        assert "test1" in recorder1.calls["GET /test"]

    def test_merge_with_data(self):
        """Merging two recorders combines all data."""
        recorder1 = ApiCallRecorder()
        recorder1.record_call("/endpoint1", "test1")
        recorder1.record_call("/shared", "test1")

        recorder2 = ApiCallRecorder()
        recorder2.record_call("/endpoint2", "test2")
        recorder2.record_call("/shared", "test2")

        recorder1.merge(recorder2)

        assert len(recorder1) == 3
        assert "test1" in recorder1.calls["GET /endpoint1"]
        assert "test2" in recorder1.calls["GET /endpoint2"]

        shared_callers = recorder1.calls["GET /shared"]
        assert "test1" in shared_callers
        assert "test2" in shared_callers
        assert len(shared_callers) == 2

    def test_to_serializable(self):
        """Convert to serializable format (sets -> lists)."""
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
        """Create from serializable format (lists -> sets)."""
        data = {"GET /test1": ["func1", "func2"], "POST /test2": ["func3"]}

        recorder = ApiCallRecorder.from_serializable(data)

        assert len(recorder) == 2
        assert "GET /test1" in recorder
        assert "POST /test2" in recorder
        assert recorder.calls["GET /test1"] == {"func1", "func2"}
        assert recorder.calls["POST /test2"] == {"func3"}

    def test_contains(self):
        """__contains__ checks for endpoint key presence."""
        recorder = ApiCallRecorder()
        recorder.record_call("/test", "func")

        assert "GET /test" in recorder
        assert "POST /test" not in recorder
        assert "GET /nonexistent" not in recorder

    def test_items(self):
        """items() iterates over (endpoint, callers) pairs."""
        recorder = ApiCallRecorder()
        recorder.record_call("/test1", "func1")
        recorder.record_call("/test2", "func2")

        items = list(recorder.items())
        assert len(items) == 2

        endpoints = [item[0] for item in items]
        assert "GET /test1" in endpoints
        assert "GET /test2" in endpoints

    def test_keys(self):
        """keys() returns all recorded endpoint keys."""
        recorder = ApiCallRecorder()
        recorder.record_call("/test1", "func1")
        recorder.record_call("/test2", "func2")

        keys = list(recorder.keys())
        assert len(keys) == 2
        assert "GET /test1" in keys
        assert "GET /test2" in keys

    def test_values(self):
        """values() returns all caller sets."""
        recorder = ApiCallRecorder()
        recorder.record_call("/test1", "func1")
        recorder.record_call("/test2", "func2")

        values = list(recorder.values())
        assert len(values) == 2

        for value in values:
            assert isinstance(value, set)


class TestEndpointDiscovery:
    """Tests for EndpointDiscovery."""

    def test_init_default(self):
        """Default init has empty endpoints."""
        discovery = EndpointDiscovery()
        assert discovery.endpoints == []
        assert discovery.discovery_source == "unknown"
        assert len(discovery) == 0

    def test_init_with_data(self):
        """Init with pre-populated endpoints."""
        endpoints = ["GET /test1", "POST /test2"]
        discovery = EndpointDiscovery(endpoints=endpoints, discovery_source="test")

        assert discovery.endpoints == endpoints
        assert discovery.discovery_source == "test"
        assert len(discovery) == 2

    def test_add_endpoint_new(self):
        """Add a new endpoint."""
        discovery = EndpointDiscovery()
        discovery.add_endpoint("/test")

        assert len(discovery) == 1
        assert "GET /test" in discovery.endpoints

    def test_add_endpoint_with_method(self):
        """Add an endpoint with a specific method."""
        discovery = EndpointDiscovery()
        discovery.add_endpoint("/test", "POST")

        assert len(discovery) == 1
        assert "POST /test" in discovery.endpoints

    def test_add_endpoint_duplicate(self):
        """Duplicate endpoints are not added twice."""
        discovery = EndpointDiscovery()
        discovery.add_endpoint("/test")
        discovery.add_endpoint("/test")

        assert len(discovery) == 1
        assert discovery.endpoints.count("GET /test") == 1

    def test_merge_empty(self):
        """Merging an empty discovery changes nothing."""
        discovery1 = EndpointDiscovery()
        discovery1.add_endpoint("/test1")

        discovery2 = EndpointDiscovery()

        discovery1.merge(discovery2)
        assert len(discovery1) == 1
        assert "GET /test1" in discovery1.endpoints

    def test_merge_with_data(self):
        """Merging combines endpoints and deduplicates."""
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


class TestSessionData:
    """Tests for SessionData."""

    def test_init_default(self):
        """Default init creates empty recorder and discovery."""
        session = SessionData()

        assert isinstance(session.recorder, ApiCallRecorder)
        assert isinstance(session.discovered_endpoints, EndpointDiscovery)
        assert len(session.recorder) == 0
        assert len(session.discovered_endpoints) == 0

    def test_record_call(self):
        """record_call delegates to recorder."""
        session = SessionData()
        session.record_call("/test", "test_func")

        assert "GET /test" in session.recorder
        assert "test_func" in session.recorder.calls["GET /test"]

    def test_record_call_with_method(self):
        """record_call with specific method."""
        session = SessionData()
        session.record_call("/test", "test_func", "POST")

        assert "POST /test" in session.recorder
        assert "test_func" in session.recorder.calls["POST /test"]

    def test_add_discovered_endpoint(self):
        """add_discovered_endpoint with method and source."""
        session = SessionData()
        session.add_discovered_endpoint("/test", "GET", "flask_adapter")

        assert "GET /test" in session.discovered_endpoints.endpoints
        assert session.discovered_endpoints.discovery_source == "flask_adapter"

    def test_add_discovered_endpoint_multiple(self):
        """Multiple discovered endpoints accumulate."""
        session = SessionData()
        session.add_discovered_endpoint("/test1", "GET", "flask_adapter")
        session.add_discovered_endpoint("/test2", "POST", "flask_adapter")

        assert len(session.discovered_endpoints) == 2
        assert "GET /test1" in session.discovered_endpoints.endpoints
        assert "POST /test2" in session.discovered_endpoints.endpoints
        assert session.discovered_endpoints.discovery_source == "flask_adapter"

    def test_merge_worker_data_dict_serializable(self):
        """Merge worker data in serializable format."""
        session = SessionData()
        session.record_call("/session", "session_test")

        worker_recorder = {"GET /worker": ["worker_test"]}
        worker_endpoints = ["POST /worker_endpoint"]

        session.merge_worker_data(worker_recorder, worker_endpoints)

        assert "GET /session" in session.recorder
        assert "GET /worker" in session.recorder
        assert "session_test" in session.recorder.calls["GET /session"]
        assert "worker_test" in session.recorder.calls["GET /worker"]

        assert "POST /worker_endpoint" in session.discovered_endpoints.endpoints

    def test_merge_worker_data_dict_raw(self):
        """Merge worker data in raw dict format."""
        session = SessionData()
        session.record_call("/session", "session_test")

        worker_recorder = {"/worker": {"worker_test"}}
        worker_endpoints = ["/worker_endpoint"]

        session.merge_worker_data(worker_recorder, worker_endpoints)

        assert "/worker" in session.recorder
        assert "worker_test" in session.recorder.calls["/worker"]

    def test_merge_worker_data_dict_mixed(self):
        """Merge worker data with mixed value types."""
        session = SessionData()

        worker_recorder = {
            "/list": ["test1", "test2"],
            "/set": {"test3"},
            "/string": "test4",
        }
        worker_endpoints = []

        session.merge_worker_data(worker_recorder, worker_endpoints)

        assert "test1" in session.recorder.calls["/list"]
        assert "test2" in session.recorder.calls["/list"]
        assert "test3" in session.recorder.calls["/set"]
        assert "test4" in session.recorder.calls["/string"]

    @pytest.mark.parametrize(
        ("worker_recorder", "worker_endpoints", "expected_recorder_len", "expected_endpoints"),
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
        """Merge worker data with edge cases (empty, non-dict, None)."""
        session = SessionData()
        if expected_recorder_len > 0:
            session.record_call("/session", "session_test")

        session.merge_worker_data(worker_recorder, worker_endpoints)

        if "GET /worker" in str(worker_recorder):
            assert "GET /worker" in session.recorder

        for endpoint in expected_endpoints:
            assert endpoint in session.discovered_endpoints.endpoints

    def test_add_discovered_endpoint_first_sets_source(self):
        """First endpoint sets the discovery source."""
        session = SessionData()
        session.add_discovered_endpoint("/first", "GET", "flask_adapter")

        assert session.discovered_endpoints.discovery_source == "flask_adapter"
        assert "GET /first" in session.discovered_endpoints.endpoints

    def test_add_discovered_endpoint_subsequent_keeps_source(self):
        """Subsequent endpoints don't change the discovery source."""
        session = SessionData()
        session.add_discovered_endpoint("/first", "GET", "flask_adapter")
        session.add_discovered_endpoint("/second", "GET", "fastapi_adapter")

        assert session.discovered_endpoints.discovery_source == "flask_adapter"
        assert "GET /first" in session.discovered_endpoints.endpoints
        assert "GET /second" in session.discovered_endpoints.endpoints
