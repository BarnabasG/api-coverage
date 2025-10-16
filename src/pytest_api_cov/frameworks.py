"""Framework adapters for Flask and FastAPI."""

from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    from .models import ApiCallRecorder


class BaseAdapter:
    def __init__(self, app: Any):
        self.app = app

    def get_endpoints(self) -> List[str]:
        """Return a list of all endpoint paths."""
        raise NotImplementedError

    def get_tracked_client(self, recorder: Optional["ApiCallRecorder"], test_name: str) -> Any:
        """Return a patched test client that records calls."""
        raise NotImplementedError


class FlaskAdapter(BaseAdapter):
    def get_endpoints(self) -> List[str]:
        excluded_rules = ("/static/<path:filename>",)
        return sorted([rule.rule for rule in self.app.url_map.iter_rules() if rule.rule not in excluded_rules])

    def get_tracked_client(self, recorder: Optional["ApiCallRecorder"], test_name: str) -> Any:
        from flask.testing import FlaskClient

        if recorder is None:
            return self.app.test_client()

        class TrackingFlaskClient(FlaskClient):
            def open(self, *args: Any, **kwargs: Any) -> Any:
                path = kwargs.get("path") or (args[0] if args else None)
                if path and hasattr(self.application.url_map, "bind"):
                    try:
                        endpoint_name, _ = self.application.url_map.bind("").match(path, method=kwargs.get("method"))
                        endpoint_rule_string = next(self.application.url_map.iter_rules(endpoint_name)).rule
                        recorder.record_call(endpoint_rule_string, test_name)  # type: ignore[union-attr]
                    except Exception:
                        pass
                return super().open(*args, **kwargs)

        return TrackingFlaskClient(self.app, self.app.response_class)


class FastAPIAdapter(BaseAdapter):
    def get_endpoints(self) -> List[str]:
        from fastapi.routing import APIRoute

        return sorted([route.path for route in self.app.routes if isinstance(route, APIRoute)])

    def get_tracked_client(self, recorder: Optional["ApiCallRecorder"], test_name: str) -> Any:
        from starlette.testclient import TestClient

        if recorder is None:
            return TestClient(self.app)

        class TrackingFastAPIClient(TestClient):
            def send(self, *args: Any, **kwargs: Any) -> Any:
                request = args[0]
                if recorder is not None:
                    recorder.record_call(request.url.path, test_name)
                return super().send(*args, **kwargs)

        return TrackingFastAPIClient(self.app)


def get_framework_adapter(app: Any) -> BaseAdapter:
    """Detects the framework and returns the appropriate adapter."""
    app_type = type(app).__name__
    module_name = getattr(type(app), "__module__", "").split(".")[0]

    if module_name == "flask" and app_type == "Flask":
        return FlaskAdapter(app)
    elif module_name == "flask_openapi3" and app_type == "OpenAPI":
        return FlaskAdapter(app)
    elif module_name == "fastapi" and app_type == "FastAPI":
        return FastAPIAdapter(app)

    raise TypeError(f"Unsupported application type: {app_type}. pytest-api-coverage supports Flask and FastAPI.")
