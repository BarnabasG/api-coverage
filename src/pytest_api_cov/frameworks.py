"""Framework adapters for Flask, FastAPI, and Django."""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from backports.strenum import StrEnum


class SupportedFramework(StrEnum):
    """String enum representing officially supported web frameworks."""

    FLASK = "flask"
    FASTAPI = "fastapi"
    DJANGO = "django"


if TYPE_CHECKING:
    from .models import ApiCallRecorder


class BaseAdapter(ABC):
    """Abstract base for framework adapters."""

    def __init__(self, app: Any) -> None:
        """Bind the framework app instance."""
        self.app = app

    @abstractmethod
    def get_endpoints(self) -> list[str]:
        """Return a list of 'METHOD /path' strings."""

    @abstractmethod
    def get_tracked_client(self, recorder: ApiCallRecorder | None, test_name: str) -> Any:
        """Return a test client that records calls."""


class FlaskAdapter(BaseAdapter):
    """Adapter for Flask applications."""

    def get_endpoints(self) -> list[str]:
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

    def get_tracked_client(self, recorder: ApiCallRecorder | None, test_name: str) -> Any:
        """Return a Flask test client with call tracking."""
        from flask.testing import FlaskClient

        if recorder is None:
            return self.app.test_client()

        url_adapter = None
        if hasattr(self.app.url_map, "bind"):
            url_adapter = self.app.url_map.bind("")

        class TrackingFlaskClient(FlaskClient):
            def open(self, *args: Any, **kwargs: Any) -> Any:
                path = kwargs.get("path") or (args[0] if args else None)
                method = kwargs.get("method", "GET").upper()

                if path and url_adapter is not None:
                    try:
                        endpoint_name, _ = url_adapter.match(path, method=method)
                        endpoint_rule_string = next(self.application.url_map.iter_rules(endpoint_name)).rule
                        recorder.record_call(endpoint_rule_string, test_name, method)  # type: ignore[union-attr]
                    except Exception:  # noqa: BLE001
                        pass
                return super().open(*args, **kwargs)

        return TrackingFlaskClient(self.app, self.app.response_class)


class FastAPIAdapter(BaseAdapter):
    """Adapter for FastAPI applications."""

    def get_endpoints(self) -> list[str]:
        """Return list of 'METHOD /path' strings."""
        endpoints: list[str] = []
        self._collect_routes(self.app.routes, "", endpoints)
        return sorted(endpoints)

    def _collect_routes(self, routes: list[Any], prefix: str, endpoints: list[str]) -> None:
        """Recursively collect endpoints from routes, including mounted sub-apps."""
        from fastapi.routing import APIRoute
        from starlette.routing import Mount

        for route in routes:
            if isinstance(route, APIRoute):
                endpoints.extend(
                    f"{method} {prefix}{route.path}" for method in route.methods if method not in ("HEAD", "OPTIONS")
                )
            elif isinstance(route, Mount):
                mount_prefix = prefix + route.path
                if hasattr(route, "routes") and route.routes:
                    self._collect_routes(route.routes, mount_prefix, endpoints)
                elif hasattr(route, "app"):
                    inner = _unwrap_wsgi_app(route.app)
                    if inner is not None:
                        sub_endpoints = get_framework_adapter(inner).get_endpoints()
                        for ep in sub_endpoints:
                            method, path = ep.split(" ", 1)
                            endpoints.append(f"{method} {mount_prefix}{path}")

    def get_tracked_client(self, recorder: ApiCallRecorder | None, test_name: str) -> Any:
        """Return a FastAPI/Starlette test client with call tracking."""
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

    def get_endpoints(self) -> list[str]:
        """Return list of 'METHOD /path' strings."""
        from django.urls import get_resolver  # type: ignore[import-untyped]
        from django.urls.resolvers import URLPattern, URLResolver  # type: ignore[import-untyped]

        endpoints: list[str] = []

        def _extract_patterns(patterns: list[Any], prefix: str = "") -> None:
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

    def get_tracked_client(self, recorder: ApiCallRecorder | None, test_name: str) -> Any:
        """Return a Django test client with call tracking."""
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


def _unwrap_wsgi_app(app: Any) -> Any:
    """Extract the inner WSGI app from middleware wrappers, if supported."""
    type_name = type(app).__name__
    if type_name in ("WSGIMiddleware", "WSGIResponder"):
        inner = getattr(app, "app", None)
        if inner is not None and is_supported_framework(inner):
            return inner
    return None


def _detect_framework(app: Any) -> SupportedFramework | None:
    """Lightweight check to detect the framework."""
    app_type = type(app).__name__
    module_name = getattr(type(app), "__module__", "").split(".")[0]

    match (module_name, app_type):
        case ("flask", "Flask") | ("flask_openapi3", "OpenAPI"):
            return SupportedFramework.FLASK
        case ("fastapi", "FastAPI"):
            return SupportedFramework.FASTAPI
        case (module, _) if module == "django" or "django" in module:
            return SupportedFramework.DJANGO
        case _:
            return None


def is_supported_framework(app: Any) -> bool:
    """Check if the app is a supported framework."""
    if app is None:
        return False
    return _detect_framework(app) is not None


def get_framework_adapter(app: Any) -> BaseAdapter:
    """Detect the framework and return the appropriate adapter."""
    match _detect_framework(app):
        case SupportedFramework.FLASK:
            return FlaskAdapter(app)
        case SupportedFramework.FASTAPI:
            return FastAPIAdapter(app)
        case SupportedFramework.DJANGO:
            return DjangoAdapter(app)
        case _:
            app_type = type(app).__name__
            raise TypeError(
                f"Unsupported application type: {app_type}. pytest-api-coverage supports Flask, FastAPI, and Django."
            )
