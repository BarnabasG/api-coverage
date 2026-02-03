"""Framework adapters for Flask and FastAPI."""

from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    from .models import ApiCallRecorder


class BaseAdapter:
    """Base adapter for framework applications."""

    def __init__(self, app: Any) -> None:
        """Initialize the adapter."""
        self.app = app

    def get_endpoints(self) -> List[str]:
        """Return a list of all endpoint paths."""
        raise NotImplementedError

    def get_tracked_client(self, recorder: Optional["ApiCallRecorder"], test_name: str) -> Any:
        """Return a patched test client that records calls."""
        raise NotImplementedError


class FlaskAdapter(BaseAdapter):
    """Adapter for Flask applications."""

    def get_endpoints(self) -> List[str]:
        """Return list of 'METHOD /path' strings."""
        excluded_rules = ("/static/<path:filename>",)
        endpoints = [
            f"{method} {rule.rule}"
            for rule in self.app.url_map.iter_rules()
            if rule.rule not in excluded_rules
            for method in rule.methods
            if method not in ("HEAD", "OPTIONS")
        ]

        return sorted(endpoints)

    def get_tracked_client(self, recorder: Optional["ApiCallRecorder"], test_name: str) -> Any:
        """Return a patched test client that records calls."""
        from flask.testing import FlaskClient

        if recorder is None:
            return self.app.test_client()

        class TrackingFlaskClient(FlaskClient):
            def open(self, *args: Any, **kwargs: Any) -> Any:
                path = kwargs.get("path") or (args[0] if args else None)
                method = kwargs.get("method", "GET").upper()

                if path and hasattr(self.application.url_map, "bind"):
                    try:
                        endpoint_name, _ = self.application.url_map.bind("").match(path, method=method)
                        endpoint_rule_string = next(self.application.url_map.iter_rules(endpoint_name)).rule
                        recorder.record_call(endpoint_rule_string, test_name, method)  # type: ignore[union-attr]
                    except Exception:  # noqa: BLE001
                        pass
                return super().open(*args, **kwargs)

        return TrackingFlaskClient(self.app, self.app.response_class)


class FastAPIAdapter(BaseAdapter):
    """Adapter for FastAPI applications."""

    def get_endpoints(self) -> List[str]:
        """Return list of 'METHOD /path' strings."""
        from fastapi.routing import APIRoute

        endpoints = [
            f"{method} {route.path}"
            for route in self.app.routes
            if isinstance(route, APIRoute)
            for method in route.methods
            if method not in ("HEAD", "OPTIONS")
        ]

        return sorted(endpoints)

    def get_tracked_client(self, recorder: Optional["ApiCallRecorder"], test_name: str) -> Any:
        """Return a patched test client that records calls."""
        from starlette.testclient import TestClient

        if recorder is None:
            return TestClient(self.app)

        class TrackingFastAPIClient(TestClient):
            def send(self, *args: Any, **kwargs: Any) -> Any:
                request = args[0]
                if recorder is not None:
                    method = request.method.upper()
                    path = request.url.path
                    recorder.record_call(path, test_name, method)
                return super().send(*args, **kwargs)

        return TrackingFastAPIClient(self.app)


class DjangoAdapter(BaseAdapter):
    """Adapter for Django applications."""

    def get_endpoints(self) -> List[str]:
        """Return list of 'METHOD /path' strings."""
        from django.urls import get_resolver  # type: ignore[import-untyped]
        from django.urls.resolvers import URLPattern, URLResolver  # type: ignore[import-untyped]

        endpoints: List[str] = []

        def _extract_patterns(patterns: List[Any], prefix: str = "") -> None:
            for pattern in patterns:
                if isinstance(pattern, URLPattern):
                    route = str(pattern.pattern).strip("^$")
                    full_path = f"/{prefix}{route}".replace("//", "/")

                    view = pattern.callback
                    methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}

                    if hasattr(view, "view_class") and hasattr(view.view_class, "http_method_names"):
                        methods = {m.upper() for m in view.view_class.http_method_names}

                    endpoints.extend(f"{method} {full_path}" for method in methods if method not in ("HEAD", "OPTIONS"))

                elif isinstance(pattern, URLResolver):
                    route = str(pattern.pattern).strip("^$")
                    _extract_patterns(pattern.url_patterns, f"{prefix}{route}")

        _extract_patterns(get_resolver().url_patterns)
        return sorted(endpoints)

    def get_tracked_client(self, recorder: Optional["ApiCallRecorder"], test_name: str) -> Any:
        """Return a patched test client that records calls."""
        from django.test import Client  # type: ignore[import-untyped]

        if recorder is None:
            return Client()

        class TrackingDjangoClient(Client):  # type: ignore[misc]
            def request(self, **request: Any) -> Any:
                method = request.get("REQUEST_METHOD", "GET").upper()
                path = request.get("PATH_INFO", "/")

                if recorder is not None:
                    recorder.record_call(path, test_name, method)

                return super().request(**request)

        return TrackingDjangoClient()


def get_framework_adapter(app: Any) -> BaseAdapter:
    """Detect the framework and return the appropriate adapter."""
    app_type = type(app).__name__
    module_name = getattr(type(app), "__module__", "").split(".")[0]

    if (module_name == "flask" and app_type == "Flask") or (module_name == "flask_openapi3" and app_type == "OpenAPI"):
        return FlaskAdapter(app)
    if module_name == "fastapi" and app_type == "FastAPI":
        return FastAPIAdapter(app)

    # Django detection
    # Django apps are often WSGIHandlers or just the module 'django' is present
    if module_name == "django" or "django" in module_name:
        return DjangoAdapter(app)

    # Check for Django WSGI handler specifically
    if app_type == "WSGIHandler" and module_name == "django.core.handlers.wsgi":
        return DjangoAdapter(app)

    raise TypeError(
        f"Unsupported application type: {app_type}. pytest-api-coverage supports Flask, FastAPI, and Django."
    )
