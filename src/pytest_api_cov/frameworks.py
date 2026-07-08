"""Framework adapters for Flask, FastAPI, and Django."""

from __future__ import annotations

import importlib
import re
import sys
from abc import ABC, abstractmethod
from itertools import count
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
    from collections.abc import Callable

    from .models import ApiCallRecorder

# Auto-added companions of GET et al. that would inflate the endpoint count.
_SKIPPED_METHODS = frozenset({"HEAD", "OPTIONS"})


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
        """Match app and blueprint static-file rules without dropping user routes sharing the name."""
        endpoint = str(getattr(rule, "endpoint", ""))
        if endpoint != "static" and not endpoint.endswith(".static"):
            return False
        # Framework static rules always end in the filename path converter.
        return str(getattr(rule, "rule", "")).endswith("/<path:filename>")

    def get_endpoints(self) -> list[str]:
        """Return list of 'METHOD /path' strings."""
        endpoints = [
            f"{method} {rule.rule}"
            for rule in self.app.url_map.iter_rules()
            if not self._is_static_rule(rule)
            for method in rule.methods
            if method not in _SKIPPED_METHODS
        ]

        return sorted(endpoints)

    def get_tracked_client(self, recorder: ApiCallRecorder | None, test_name: str) -> Any:
        """Return a Flask test client with call tracking."""
        from urllib.parse import urlsplit

        from flask.testing import FlaskClient
        from werkzeug.routing import RequestRedirect

        if recorder is None:
            return self.app.test_client()

        active_recorder = recorder
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
                        active_recorder.record_call(rule.rule, test_name, method)
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
            # APIRoutes always count; plain Starlette routes count unless flagged out of
            # the schema (the auto-generated /docs, /openapi.json, ... routes are).
            if isinstance(route, APIRoute) or (isinstance(route, Route) and getattr(route, "include_in_schema", True)):
                methods = route.methods or {"GET"}
                endpoints.extend(
                    f"{method} {prefix}{route.path}" for method in methods if method not in _SKIPPED_METHODS
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

        active_recorder = recorder

        class TrackingFastAPIClient(TestClient):
            def send(self, *args: Any, **kwargs: Any) -> Any:
                request = args[0]
                method = request.method.upper()
                original_path = request.url.path
                try:
                    response = super().send(*args, **kwargs)
                except BaseException:
                    active_recorder.record_call(original_path, test_name, method)
                    raise
                # The requested endpoint always gets credit (it may itself be a
                # redirecting route); httpx follows redirects inside send(), so a
                # followed redirect also credits the final route it landed on.
                active_recorder.record_call(original_path, test_name, method)
                final_request = getattr(response, "request", None)
                if final_request is not None:
                    final_path = getattr(getattr(final_request, "url", None), "path", None)
                    if final_path and final_path != original_path:
                        active_recorder.record_call(final_path, test_name, final_request.method.upper())
                return response

        return TrackingFastAPIClient(self.app)


_REGEX_SHORTHAND_CLASSES = frozenset("dDwWsS")
_QUANTIFIER_PATTERN = re.compile(r"[+*?]|\{\d+(?:,\d*)?\}")


def _consume_quantifier(route: str, i: int) -> int:
    """Return the index just past a regex quantifier starting at ``i``, if any."""
    match = _QUANTIFIER_PATTERN.match(route, i)
    return match.end() if match else i


def _skip_class(route: str, i: int) -> int:
    """Return the index of the ']' closing the character class opened at ``route[i]``."""
    j = i + 1
    while j < len(route) and route[j] != "]":
        j += 2 if route[j] == "\\" else 1
    return j


def _group_placeholder(group: str, next_param: Callable[[], str]) -> str:
    """Choose a placeholder for a regex group; bodies that can span '/' get a path converter."""
    named = re.match(r"\(\?P<(\w+)>", group)
    body = group[named.end() : -1] if named else group[1:-1]
    multi_segment = "/" in body or re.search(r"(?<!\\)\.", body) is not None or "\\S" in body
    name = named.group(1) if named else next_param()
    return f"<path:{name}>" if multi_segment else f"<{name}>"


def _django_route_to_template(route: str) -> str:
    r"""Convert a Django route string to a matchable template.

    ``path()`` routes pass through unchanged. In ``re_path()`` regexes, groups
    (``(?P<year>[0-9]{4})``), shorthand classes (``\d+``), bare character
    classes (``[0-9]+``) and bare dots become placeholders (``path:`` variants
    when the pattern can span ``/``); escaped literals (``\.``) are unescaped
    and bare quantifiers (a trailing ``/?``) are dropped, so recorded request
    paths can match the template.
    """
    out: list[str] = []
    i = 0
    n = len(route)
    param_counter = count(1)

    def next_param() -> str:
        return f"param{next(param_counter)}"

    while i < n:
        char = route[i]
        if char == "\\" and i + 1 < n:
            escaped = route[i + 1]
            if escaped in _REGEX_SHORTHAND_CLASSES:
                out.append(f"<{next_param()}>")
                i = _consume_quantifier(route, i + 2)
            else:
                out.append(escaped)
                i += 2
        elif char == "(":
            depth = 0
            j = i
            while j < n:
                inner = route[j]
                if inner == "\\":
                    j += 2
                    continue
                if inner == "[":
                    j = _skip_class(route, j)
                elif inner == "(":
                    depth += 1
                elif inner == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            out.append(_group_placeholder(route[i : j + 1], next_param))
            i = _consume_quantifier(route, j + 1)
        elif char == "[":
            j = _skip_class(route, i)
            out.append(f"<{next_param()}>")
            i = _consume_quantifier(route, j + 1)
        elif char == ".":
            end = _consume_quantifier(route, i + 1)
            # A quantified dot (.* / .+) can cross path segments.
            out.append(f"<path:{next_param()}>" if end > i + 1 else f"<{next_param()}>")
            i = end
        elif char in "+*?":
            # Bare quantifier on the preceding literal (e.g. a trailing '/?'): drop it.
            i += 1
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
                        implemented = {m.upper() for m in view_class.http_method_names if hasattr(view_class, m)}
                        if implemented - _SKIPPED_METHODS:
                            methods = implemented
                        # else: dispatch()-only view — keep the default set so the
                        # endpoint stays discoverable at all.

                    endpoints.extend(f"{method} {full_path}" for method in methods if method not in _SKIPPED_METHODS)

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

        active_recorder = recorder

        class TrackingDjangoClient(Client):  # type: ignore[misc]
            def request(self, **request: Any) -> Any:
                method = request.get("REQUEST_METHOD", "GET").upper()
                path = request.get("PATH_INFO", "/")

                active_recorder.record_call(path, test_name, method)

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


_FRAMEWORK_CLASS_SPECS: tuple[tuple[SupportedFramework, str, str], ...] = (
    (SupportedFramework.FLASK, "flask", "Flask"),
    (SupportedFramework.FASTAPI, "fastapi", "FastAPI"),
    (SupportedFramework.DJANGO, "django.core.handlers.base", "BaseHandler"),
)

_import_failed: set[str] = set()


def _optional_class(module_name: str, attr: str) -> type[Any] | None:
    """Resolve a class from an optional dependency.

    Resolves through sys.modules so reloaded modules stay consistent, and
    remembers failed imports so missing frameworks are only probed once.
    """
    if module_name in _import_failed:
        return None
    module = sys.modules.get(module_name)
    if module is None:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            _import_failed.add(module_name)
            return None
    cls = getattr(module, attr, None)
    return cls if isinstance(cls, type) else None


def _detect_framework(app: Any) -> SupportedFramework | None:
    """Detect the framework, supporting app subclasses via isinstance checks."""
    if app is None:
        return None

    for framework, module_name, attr in _FRAMEWORK_CLASS_SPECS:
        framework_class = _optional_class(module_name, attr)
        if framework_class is not None and isinstance(app, framework_class):
            return framework

    # Name-based fallback for duck-typed apps (e.g. mocks in test suites).
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
