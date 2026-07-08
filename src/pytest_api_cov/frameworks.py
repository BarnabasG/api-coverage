"""Framework adapters for Flask, FastAPI, and Django."""

from __future__ import annotations

import importlib
import sys
from abc import ABC, abstractmethod
from itertools import count
from typing import TYPE_CHECKING, Any

if sys.version_info >= (3, 11):
    from enum import StrEnum

    # The regex parser module was renamed from sre_parse in 3.11; typeshed does not declare it.
    from re import _parser as _sre_parser  # type: ignore[attr-defined]
else:
    import sre_parse as _sre_parser

    from backports.strenum import StrEnum


class SupportedFramework(StrEnum):
    """String enum representing officially supported web frameworks."""

    FLASK = "flask"
    FASTAPI = "fastapi"
    DJANGO = "django"


if TYPE_CHECKING:
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


def _class_matches_slash(items: Any) -> bool:
    """Report whether a character class (the ``av`` of an IN node) can match '/'."""
    slash = ord("/")
    negated = bool(items) and items[0][0] is _sre_parser.NEGATE
    matched = any(
        (op is _sre_parser.LITERAL and av == slash)
        or (op is _sre_parser.RANGE and av[0] <= slash <= av[1])
        or (
            op is _sre_parser.CATEGORY
            and av
            in (
                _sre_parser.CATEGORY_NOT_WORD,
                _sre_parser.CATEGORY_NOT_DIGIT,
                _sre_parser.CATEGORY_NOT_SPACE,
            )
        )
        for op, av in items
    )
    return not matched if negated else matched


def _can_match_slash(nodes: Any) -> bool:
    """Report whether this parsed regex subtree can match '/', i.e. span path segments."""
    return any(
        op is _sre_parser.ANY
        or (op is _sre_parser.LITERAL and av == ord("/"))
        or (op is _sre_parser.NOT_LITERAL and av != ord("/"))
        or (op is _sre_parser.IN and _class_matches_slash(av))
        or (op is _sre_parser.SUBPATTERN and _can_match_slash(av[3]))
        or (op is _sre_parser.BRANCH and any(_can_match_slash(branch) for branch in av[1]))
        or (op in (_sre_parser.MAX_REPEAT, _sre_parser.MIN_REPEAT) and _can_match_slash(av[2]))
        for op, av in nodes
    )


def _django_route_to_template(route: str) -> str:
    r"""Convert a Django route string to a matchable template.

    ``path()`` routes (pure literals) pass through unchanged. ``re_path()``
    regexes are parsed with the stdlib regex parser, and every dynamic
    construct — groups (``(?P<year>[0-9]{4})``), classes (``[0-9]+``),
    shorthand (``\d+``), dots, alternations — becomes a placeholder,
    ``<path:...>`` when it can span ``/``. Escaped literals (``\.``) are
    unescaped and an optional trailing ``/?`` keeps its literal, so recorded
    request paths can match the template. Unparseable input passes through
    verbatim.
    """
    try:
        parsed = _sre_parser.parse(route)
    except Exception:  # noqa: BLE001 - not a regex (e.g. a literal path() route with specials)
        return route

    group_names = {number: name for name, number in parsed.state.groupdict.items()}
    param_counter = count(1)

    def next_param() -> str:
        return f"param{next(param_counter)}"

    def placeholder(nodes: Any, name: str | None = None) -> str:
        name = name or next_param()
        return f"<path:{name}>" if _can_match_slash(nodes) else f"<{name}>"

    def emit(nodes: Any) -> str:
        out: list[str] = []
        for op, av in nodes:
            if op is _sre_parser.LITERAL:
                # Escaped literals (\.) arrive pre-unescaped from the parser.
                out.append(chr(av))
            elif op is _sre_parser.AT:
                continue  # anchors (^, $, \b) never appear in request paths
            elif op is _sre_parser.SUBPATTERN:
                group_number, _add_flags, _del_flags, body = av
                out.append(placeholder(body, group_names.get(group_number)))
            elif op in (_sre_parser.MAX_REPEAT, _sre_parser.MIN_REPEAT):
                _min_count, max_count, body = av
                if max_count == 1 and len(body) == 1 and body[0][0] is _sre_parser.LITERAL:
                    out.append(chr(body[0][1]))  # an optional literal ('/?') keeps its literal
                elif len(body) == 1 and body[0][0] is _sre_parser.SUBPATTERN:
                    out.append(emit(body))  # '(...)?' is just the group placeholder
                else:
                    out.append(placeholder(body))  # \d+, [0-9]+, .*, a{2,4}, ...
            else:
                # IN, ANY, BRANCH, NOT_LITERAL — and any opcode a future Python adds.
                out.append(placeholder([(op, av)]))
        return "".join(out)

    return emit(parsed)


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
