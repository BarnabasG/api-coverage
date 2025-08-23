"""src/pytest_api_cov/frameworks.py"""

from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    from .models import ApiCallRecorder


# --- Base Adapter ---
class BaseAdapter:
    def __init__(self, app: Any):
        self.app = app

    def get_endpoints(self) -> List[str]:
        """Return a list of all endpoint paths."""
        raise NotImplementedError

    def get_tracked_client(self, recorder: Optional[ApiCallRecorder], test_name: str) -> Any:
        """Return a patched test client that records calls."""
        raise NotImplementedError


# --- Flask Adapter ---
class FlaskAdapter(BaseAdapter):
    def get_endpoints(self) -> List[str]:
        # Exclude static and other non-API endpoints
        excluded_rules = ("/static/<path:filename>",)
        return sorted([rule.rule for rule in self.app.url_map.iter_rules() if rule.rule not in excluded_rules])

    def get_tracked_client(self, recorder: Optional[ApiCallRecorder], test_name: str) -> Any:
        from flask.testing import FlaskClient

        if recorder is None:
            return self.app.test_client()

        class TrackingFlaskClient(FlaskClient):
            def open(self, *args, **kwargs):
                path = kwargs.get("path") or (args[0] if args else None)
                if path and hasattr(self.application.url_map, "bind"):
                    try:
                        # Fetch the endpoint *name*, e.g., 'root' not '/'
                        endpoint_name, _ = self.application.url_map.bind("").match(path, method=kwargs.get("method"))
                        # Find the rule object associated with that endpoint name
                        endpoint_rule_string = next(self.application.url_map.iter_rules(endpoint_name)).rule
                        recorder.record_call(endpoint_rule_string, test_name)
                    except Exception:
                        # Fallback for paths that might not match a rule
                        pass
                return super().open(*args, **kwargs)

        return TrackingFlaskClient(self.app, self.app.response_class)


# --- FastAPI Adapter ---
class FastAPIAdapter(BaseAdapter):
    def get_endpoints(self) -> List[str]:
        from fastapi.routing import APIRoute

        return sorted([route.path for route in self.app.routes if isinstance(route, APIRoute)])

    def get_tracked_client(self, recorder: Optional[ApiCallRecorder], test_name: str) -> Any:
        from starlette.testclient import TestClient

        if recorder is None:
            return TestClient(self.app)

        # FastAPI patches the 'send' method of the underlying client
        class TrackingFastAPIClient(TestClient):
            def send(self, *args, **kwargs):
                request = args[0]
                recorder.record_call(request.url.path, test_name)
                return super().send(*args, **kwargs)

        return TrackingFastAPIClient(self.app)


# --- Factory Function ---
def get_framework_adapter(app: Any) -> BaseAdapter:
    """Detects the framework and returns the appropriate adapter."""
    app_type = type(app).__name__
    module_name = getattr(type(app), "__module__", "").split(".")[0]

    if module_name == "flask" and app_type == "Flask":
        return FlaskAdapter(app)
    elif module_name == "fastapi" and app_type == "FastAPI":
        return FastAPIAdapter(app)

    raise TypeError(f"Unsupported application type: {app_type}. pytest-api-coverage supports Flask and FastAPI.")
