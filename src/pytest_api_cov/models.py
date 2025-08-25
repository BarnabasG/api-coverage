"""Data models for pytest-api-cov."""

from typing import Any, Dict, Iterator, List, Set, Tuple

from pydantic import BaseModel, Field


class ApiCallRecorder(BaseModel):
    """Model for tracking API endpoint calls during testing."""

    model_config = {"arbitrary_types_allowed": True}

    calls: Dict[str, Set[str]] = Field(default_factory=dict)

    def record_call(self, endpoint: str, test_name: str) -> None:
        """Record that a test called an endpoint."""
        if endpoint not in self.calls:
            self.calls[endpoint] = set()
        self.calls[endpoint].add(test_name)

    def get_called_endpoints(self) -> List[str]:
        """Get list of all endpoints that have been called."""
        return list(self.calls.keys())

    def get_callers(self, endpoint: str) -> Set[str]:
        """Get the set of test names that called a specific endpoint."""
        return self.calls.get(endpoint, set())

    def merge(self, other: "ApiCallRecorder") -> None:
        """Merge another recorder's data into this one."""
        for endpoint, callers in other.calls.items():
            if endpoint not in self.calls:
                self.calls[endpoint] = set()
            self.calls[endpoint].update(callers)

    def to_serializable(self) -> Dict[str, List[str]]:
        """Convert to a serializable format (sets -> lists) for worker communication."""
        return {endpoint: list(callers) for endpoint, callers in self.calls.items()}

    @classmethod
    def from_serializable(cls, data: Dict[str, List[str]]) -> "ApiCallRecorder":
        """Create from serializable format (lists -> sets)."""
        calls = {endpoint: set(callers) for endpoint, callers in data.items()}
        return cls(calls=calls)

    def __len__(self) -> int:
        """Return number of endpoints recorded."""
        return len(self.calls)

    def __contains__(self, endpoint: str) -> bool:
        """Check if an endpoint has been recorded."""
        return endpoint in self.calls

    def items(self) -> Iterator[Tuple[str, Set[str]]]:
        """Iterate over endpoint, callers pairs."""
        return self.calls.items()

    def keys(self) -> Iterator[str]:
        """Get all recorded endpoints."""
        return self.calls.keys()

    def values(self) -> Iterator[Set[str]]:
        """Get all caller sets."""
        return self.calls.values()


class EndpointDiscovery(BaseModel):
    """Model for discovered API endpoints."""

    endpoints: List[str] = Field(default_factory=list)
    discovery_source: str = Field(default="unknown")

    def add_endpoint(self, endpoint: str) -> None:
        """Add a discovered endpoint."""
        if endpoint not in self.endpoints:
            self.endpoints.append(endpoint)

    def merge(self, other: "EndpointDiscovery") -> None:
        """Merge another discovery's endpoints into this one."""
        for endpoint in other.endpoints:
            self.add_endpoint(endpoint)

    def __len__(self) -> int:
        """Return number of discovered endpoints."""
        return len(self.endpoints)

    def __iter__(self) -> Iterator[str]:  # type: ignore[override]
        """Iterate over discovered endpoints."""
        return iter(self.endpoints)


class SessionData(BaseModel):
    """Model for session-level API coverage data."""

    recorder: ApiCallRecorder = Field(default_factory=ApiCallRecorder)
    discovered_endpoints: EndpointDiscovery = Field(default_factory=EndpointDiscovery)

    def record_call(self, endpoint: str, test_name: str) -> None:
        """Record an API call."""
        self.recorder.record_call(endpoint, test_name)

    def add_discovered_endpoint(self, endpoint: str, source: str = "unknown") -> None:
        """Add a discovered endpoint."""
        if not self.discovered_endpoints.endpoints:
            self.discovered_endpoints.discovery_source = source
        self.discovered_endpoints.add_endpoint(endpoint)

    def merge_worker_data(self, worker_recorder: Dict[str, Any], worker_endpoints: List[str]) -> None:
        """Merge data from a worker process."""
        if isinstance(worker_recorder, dict):
            all_lists = worker_recorder and all(isinstance(v, list) for v in worker_recorder.values())
            if all_lists:
                worker_api_recorder = ApiCallRecorder.from_serializable(worker_recorder)
            else:
                calls = {k: set(v) if isinstance(v, (list, set)) else {v} for k, v in worker_recorder.items()}
                worker_api_recorder = ApiCallRecorder(calls=calls)

            self.recorder.merge(worker_api_recorder)

        if worker_endpoints:
            worker_discovery = EndpointDiscovery(endpoints=worker_endpoints, discovery_source="worker")
            self.discovered_endpoints.merge(worker_discovery)
