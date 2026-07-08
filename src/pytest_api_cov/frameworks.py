"""Framework adapters for Flask, FastAPI, and Django."""

from __future__ import annotations

import re
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

    @staticmethod
    def _is_static_rule(rule: Any) -> bool:
        """Match app and blueprint static rules by endpoint name, covering custom static_url_path."""
        endpoint = str(getattr(rule, "endpoint", ""))
        return endpoint == "static" or endpoint.endswith(".static")

    def get_endpoints(self) -> list[str]:
        """Return list of 'METHOD /path' strings."""
        endpoints = [
            f"{method} {rule.rule}"
            for rule in self.app.url_map.iter_rules()
            if not self._is_static_rule(rule)
            for method in rule.methods
            if method not in ("HEAD", "OPTIONS")
        ]

        return sorted(endpoints)

    def get_tracked_client(self, recorder: ApiCallRecorder | None, test_name: str) -> Any:
        """Return a Flask test client with call tracking."""
        from urllib.parse import urlsplit

        from flask.testing import FlaskClient
        from werkzeug.routing import RequestRedirect

        if recorder is None:
            return self.app.test_client()

        url_adapter = None
        if hasattr(self.app.url_map, "bind"):
            url_adapter = self.app.url_map.bind("")

        def _match_rule(path: str, method: str, follow_redirects: bool) -> Any | None:
            try:
                rule, _ = url_adapter.match(path, method=method, return_rule=True)  # type: ignore[union-attr]
            except RequestRedirect as redirect:
                # A trailing-slash redirect only reaches the view when redirects are followed.
                if not follow_redirects:
                    return None
                try:
                    rule, _ = url_adapter.match(  # type: ignore[union-attr]
                        urlsplit(redirect.new_url).path, method=method, return_rule=True
                    )
                except Exception:  # noqa: BLE001
                    return None
            except Exception:  # noqa: BLE001
                return None
            return rule

        class TrackingFlaskClient(FlaskClient):
            def open(self, *args: Any, **kwargs: Any) -> Any:
                path = kwargs.get("path") or (args[0] if args else None)
                method = kwargs.get("method", "GET").upper()

                if isinstance(path, str) and url_adapter is not None:
                    rule = _match_rule(path.partition("?")[0], method, bool(kwargs.get("follow_redirects")))
                    if rule is not None:
                        recorder.record_call(rule.rule, test_name, method)  # type: ignore[union-attr]
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
        from starlette.routing import Mount, Route

        for route in routes:
            if isinstance(route, APIRoute):
                endpoints.extend(
                    f"{method} {prefix}{route.path}" for method in route.methods if method not in ("HEAD", "OPTIONS")
                )
            elif isinstance(route, Route) and not isinstance(route, Mount):
                # Plain Starlette routes (add_route, mounted Starlette apps). The auto-generated
                # docs routes (/docs, /openapi.json, ...) carry include_in_schema=False.
                if not getattr(route, "include_in_schema", True):
                    continue
                methods = route.methods or {"GET"}
                endpoints.extend(
                    f"{method} {prefix}{route.path}" for method in methods if method not in ("HEAD", "OPTIONS")
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
                try:
                    response = super().send(*args, **kwargs)
                except BaseException:
                    if recorder is not None:
                        recorder.record_call(request.url.path, test_name, request.method.upper())
                    raise
                if recorder is not None:
                    # httpx follows redirects inside send(); response.request points at the
                    # final request, so followed slash-redirects record the real route path.
                    final_request = getattr(response, "request", request)
                    recorder.record_call(final_request.url.path, test_name, final_request.method.upper())
                return response

        return TrackingFastAPIClient(self.app)


def _django_route_to_template(route: str) -> str:
    r"""Convert a Django route string to a matchable template.

    ``path()`` routes pass through unchanged; ``re_path()`` regex groups
    (``(?P<year>[0-9]{4})``) become ``<year>`` placeholders and escaped
    literals (``\.``) are unescaped so recorded request paths can match.
    """
    out: list[str] = []
    i = 0
    param_count = 0
    n = len(route)
    while i < n:
        char = route[i]
        if char == "\\" and i + 1 < n:
            out.append(route[i + 1])
            i += 2
        elif char == "(":
            depth = 0
            j = i
            in_class = False
            while j < n:
                inner = route[j]
                if inner == "\\":
                    j += 2
                    continue
                if in_class:
                    in_class = inner != "]"
                elif inner == "[":
                    in_class = True
                elif inner == "(":
                    depth += 1
                elif inner == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            named = re.match(r"\(\?P<(\w+)>", route[i : j + 1])
            if named:
                out.append(f"<{named.group(1)}>")
            else:
                param_count += 1
                out.append(f"<param{param_count}>")
            i = j + 1
        else:
            out.append(char)
            i += 1
    return "".join(out)


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
                    route = _django_route_to_template(str(pattern.pattern).strip("^$"))
                    full_path = f"/{prefix}{route}".replace("//", "/")

                    view = pattern.callback
                    methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}

                    view_class = getattr(view, "view_class", None)
                    if view_class is not None and hasattr(view_class, "http_method_names"):
                        # Only count methods the class actually implements (mirrors
                        # View._allowed_methods), not the full http_method_names list.
                        methods = {m.upper() for m in view_class.http_method_names if hasattr(view_class, m)}

                    endpoints.extend(f"{method} {full_path}" for method in methods if method not in ("HEAD", "OPTIONS"))

                elif isinstance(pattern, URLResolver):
                    route = _django_route_to_template(str(pattern.pattern).strip("^$"))
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


def _detect_by_isinstance(app: Any) -> SupportedFramework | None:
    """Detect Flask/FastAPI apps (including subclasses) via isinstance checks."""
    try:
        from flask import Flask

        if isinstance(app, Flask):
            return SupportedFramework.FLASK
    except ImportError:
        pass

    try:
        from fastapi import FastAPI

        if isinstance(app, FastAPI):
            return SupportedFramework.FASTAPI
    except ImportError:
        pass

    return None


def _detect_framework(app: Any) -> SupportedFramework | None:
    """Detect the framework, supporting app subclasses via isinstance checks."""
    if app is None:
        return None

    framework = _detect_by_isinstance(app)
    if framework is not None:
        return framework

    # Name-based fallback for Django handlers and duck-typed apps.
    app_type = type(app).__name__
    module_name = getattr(type(app), "__module__", "").split(".")[0]

    match (module_name, app_type):
        case ("flask", "Flask") | ("flask_openapi3", "OpenAPI"):
            return SupportedFramework.FLASK
        case ("fastapi", "FastAPI"):
            return SupportedFramework.FASTAPI
        case ("django", _):
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
