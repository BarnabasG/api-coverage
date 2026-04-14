"""Data models for pytest-api-cov."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, PrivateAttr


class ApiCallRecorder(BaseModel):
    """Tracks API endpoint calls during testing."""

    model_config = {"arbitrary_types_allowed": True}

    calls: dict[str, set[str]] = Field(default_factory=dict)

    def record_call(self, endpoint: str, test_name: str, method: str = "GET") -> None:
        """Record that a test called a specific method+endpoint."""
        key = self._format_endpoint_key(method, endpoint)
        self.calls.setdefault(key, set()).add(test_name)

    @staticmethod
    def _format_endpoint_key(method: str, endpoint: str) -> str:
        """Format method and endpoint into a consistent key."""
        return f"{method.upper()} {endpoint}"

    @staticmethod
    def _parse_endpoint_key(endpoint_key: str) -> tuple[str, str]:
        """Parse an endpoint key back into (method, endpoint)."""
        if " " in endpoint_key:
            method, endpoint = endpoint_key.split(" ", 1)
            return method, endpoint
        return "GET", endpoint_key

    def merge(self, other: ApiCallRecorder) -> None:
        """Merge another recorder's data into this one."""
        for endpoint, callers in other.calls.items():
            self.calls.setdefault(endpoint, set()).update(callers)

    def to_serializable(self) -> dict[str, list[str]]:
        """Convert to serializable format (sets -> lists) for worker communication."""
        return {endpoint: list(callers) for endpoint, callers in self.calls.items()}

    @classmethod
    def from_serializable(cls, data: dict[str, list[str]]) -> ApiCallRecorder:
        """Create from serializable format (lists -> sets)."""
        calls = {endpoint: set(callers) for endpoint, callers in data.items()}
        return cls(calls=calls)

    def __len__(self) -> int:
        """Return the number of distinct endpoints recorded."""
        return len(self.calls)

    def __contains__(self, endpoint: str) -> bool:
        """Check if an endpoint has been recorded."""
        return endpoint in self.calls

    def items(self) -> Any:
        """Iterate over (endpoint, callers) pairs."""
        return self.calls.items()

    def keys(self) -> Any:
        """Get all recorded endpoints."""
        return self.calls.keys()

    def values(self) -> Any:
        """Get all caller sets."""
        return self.calls.values()


class EndpointDiscovery(BaseModel):
    """Discovered API endpoints."""

    endpoints: list[str] = Field(default_factory=list)
    _seen: set[str] = PrivateAttr(default_factory=set)
    discovery_source: str = Field(default="unknown")

    def model_post_init(self, _: Any, /) -> None:
        """Sync the internal set with any pre-populated endpoints."""
        self._seen = set(self.endpoints)

    def add_endpoint(self, endpoint: str, method: str = "GET") -> None:
        """Add a discovered endpoint if not already present."""
        key = ApiCallRecorder._format_endpoint_key(method, endpoint)
        if key not in self._seen:
            self._seen.add(key)
            self.endpoints.append(key)

    def merge(self, other: EndpointDiscovery) -> None:
        """Merge another discovery's endpoints into this one."""
        for endpoint in other.endpoints:
            if endpoint not in self._seen:
                self._seen.add(endpoint)
                self.endpoints.append(endpoint)

    def __len__(self) -> int:
        """Return the number of discovered endpoints."""
        return len(self.endpoints)


class SessionData(BaseModel):
    """Session-level API coverage data."""

    recorder: ApiCallRecorder = Field(default_factory=ApiCallRecorder)
    discovered_endpoints: EndpointDiscovery = Field(default_factory=EndpointDiscovery)

    def record_call(self, endpoint: str, test_name: str, method: str = "GET") -> None:
        """Record an API call."""
        self.recorder.record_call(endpoint, test_name, method)

    def add_discovered_endpoint(self, endpoint: str, method: str = "GET", source: str = "unknown") -> None:
        """Add a discovered endpoint."""
        if not self.discovered_endpoints.endpoints:
            self.discovered_endpoints.discovery_source = source
        self.discovered_endpoints.add_endpoint(endpoint, method)

    def merge_worker_data(self, worker_recorder: dict[str, Any], worker_endpoints: list[str]) -> None:
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
