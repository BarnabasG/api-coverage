"""Tests for framework adapters."""

from unittest.mock import Mock, patch

import pytest

from pytest_api_cov.frameworks import BaseAdapter, FastAPIAdapter, FlaskAdapter, get_framework_adapter


class MockFlaskRule:
    def __init__(self, rule, methods=None):
        self.rule = rule
        self.methods = methods or {"GET", "POST", "HEAD", "OPTIONS"}


class MockFlaskURLMap:
    def iter_rules(self):
        return [MockFlaskRule("/"), MockFlaskRule("/users/<id>")]


class MockFastAPIRoute:
    def __init__(self, path, methods=None):
        self.path = path
        self.methods = methods or {"GET", "POST"}


class TestFlaskAdapter:
    """Tests for the Flask adapter."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_app = Mock()
        self.mock_app.__module__ = "flask"
        type(self.mock_app).__name__ = "Flask"
        self.mock_app.url_map = MockFlaskURLMap()
        self.adapter = FlaskAdapter(self.mock_app)

    def test_flask_get_endpoints(self):
        """Discover Flask endpoints."""
        endpoints = self.adapter.get_endpoints()
        expected = ["GET /", "GET /users/<id>", "POST /", "POST /users/<id>"]
        assert sorted(endpoints) == sorted(expected)

    def test_flask_get_tracked_client_no_recorder(self):
        """No recorder returns a normal test client."""
        client = self.adapter.get_tracked_client(None, "test_name")
        assert client == self.mock_app.test_client()

    def test_flask_get_tracked_client_with_recorder(self):
        """Recorder returns a TrackingFlaskClient."""
        self.mock_app.response_class = type("MockResponse", (), {})

        recorder = {}
        client = self.adapter.get_tracked_client(recorder, "test_name")
        assert hasattr(client, "open")
        assert "TrackingFlaskClient" in str(type(client))

    def test_flask_tracking_client_open_method(self):
        """TrackingFlaskClient.open forwards calls."""
        with patch("flask.testing.FlaskClient"):
            recorder = {}
            client = self.adapter.get_tracked_client(recorder, "test_name")

            client.open = Mock(return_value="response")

            response = client.open(path="/test", method="GET")
            assert response == "response"

            response = client.open("/test2", method="POST")
            assert response == "response"

    def test_flask_tracking_client_exception_handling(self):
        """Exceptions during URL matching are silently caught."""
        self.mock_app.response_class = type("MockResponse", (), {})

        recorder = {}
        client = self.adapter.get_tracked_client(recorder, "test_func")

        with (
            patch.object(client.__class__.__bases__[0], "open", return_value=Mock()) as mock_super_open,
            patch.object(self.mock_app.url_map, "iter_rules", side_effect=Exception("Unexpected error")),
        ):
            client.open("/test", method="GET")

        mock_super_open.assert_called_once()
        assert recorder == {}


class TestFastAPIAdapter:
    """Tests for the FastAPI adapter."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_app = Mock()
        self.mock_app.__module__ = "fastapi"
        type(self.mock_app).__name__ = "FastAPI"

        self.mock_app.routes = [
            MockFastAPIRoute("/"),
            MockFastAPIRoute("/items/{item_id}"),
            Mock(path="/docs"),
        ]
        type(self.mock_app.routes[2]).__name__ = "HTMLRoute"

        self.adapter = FastAPIAdapter(self.mock_app)

    def test_fastapi_get_endpoints(self):
        """Discover FastAPI endpoints."""
        with patch("fastapi.routing.APIRoute", MockFastAPIRoute):
            endpoints = self.adapter.get_endpoints()
            expected = ["GET /", "GET /items/{item_id}", "POST /", "POST /items/{item_id}"]
            assert sorted(endpoints) == sorted(expected)

    def test_fastapi_get_tracked_client_no_recorder(self):
        """No recorder returns a normal TestClient."""
        with patch("starlette.testclient.TestClient") as MockTestClient:
            self.adapter.get_tracked_client(None, "test_name")
            MockTestClient.assert_called_once_with(self.mock_app)

    def test_fastapi_get_tracked_client_with_recorder(self):
        """Recorder returns a TrackingFastAPIClient."""
        recorder = {}
        client = self.adapter.get_tracked_client(recorder, "test_name")
        assert hasattr(client, "send")
        assert "TrackingFastAPIClient" in str(type(client))

    def test_fastapi_tracking_client_send_method(self):
        """TrackingFastAPIClient.send records calls and forwards."""
        from pytest_api_cov.models import ApiCallRecorder

        recorder = ApiCallRecorder()
        client = self.adapter.get_tracked_client(recorder, "test_name")

        assert hasattr(client, "send")
        assert callable(client.send)

        with patch.object(client.__class__.__bases__[0], "send", return_value="response") as mock_send:
            mock_request = Mock()
            mock_request.method = "GET"
            mock_request.url.path = "/test"

            response = client.send(mock_request)
            assert response == "response"
            mock_send.assert_called_once_with(mock_request)
            assert "GET /test" in recorder.calls


class TestBaseAdapter:
    """Tests for the abstract base adapter."""

    def test_base_adapter_cannot_be_instantiated(self):
        """BaseAdapter is abstract and cannot be instantiated directly."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            BaseAdapter(None)

    def test_base_adapter_subclass_must_implement_methods(self):
        """Subclasses missing abstract methods cannot be instantiated."""

        class PartialAdapter(BaseAdapter):
            def get_endpoints(self):
                return []

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            PartialAdapter(None)

    def test_base_adapter_complete_subclass(self):
        """Subclasses implementing all methods can be instantiated."""

        class CompleteAdapter(BaseAdapter):
            def get_endpoints(self):
                return []

            def get_tracked_client(self, recorder, test_name):
                return None

        adapter = CompleteAdapter(None)
        assert adapter.get_endpoints() == []
        assert adapter.get_tracked_client(None, "test") is None


class TestAdapterFactory:
    """Tests for the adapter factory function."""

    def test_get_framework_adapter(self):
        """Factory returns correct adapter per framework."""
        mock_flask_app = Mock()
        mock_flask_app.__class__.__module__ = "flask.app"
        mock_flask_app.__class__.__name__ = "Flask"

        mock_fastapi_app = Mock()
        mock_fastapi_app.__class__.__module__ = "fastapi.applications"
        mock_fastapi_app.__class__.__name__ = "FastAPI"

        mock_django_app = Mock()
        mock_django_app.__class__.__module__ = "django.core.handlers.wsgi"
        mock_django_app.__class__.__name__ = "WSGIHandler"

        mock_unsupported_app = Mock()
        mock_unsupported_app.__class__.__module__ = "bottle"
        mock_unsupported_app.__class__.__name__ = "Bottle"

        assert isinstance(get_framework_adapter(mock_flask_app), FlaskAdapter)
        assert isinstance(get_framework_adapter(mock_fastapi_app), FastAPIAdapter)

        from pytest_api_cov.frameworks import DjangoAdapter

        assert isinstance(get_framework_adapter(mock_django_app), DjangoAdapter)

        with pytest.raises(TypeError, match="Unsupported application type"):
            get_framework_adapter(mock_unsupported_app)

    def test_get_framework_adapter_with_missing_module(self):
        """App without __module__ raises TypeError."""
        mock_app = Mock()
        mock_class = Mock()
        mock_class.__name__ = "UnknownApp"
        del mock_class.__module__
        mock_app.__class__ = mock_class

        with pytest.raises(TypeError, match="Unsupported application type"):
            get_framework_adapter(mock_app)


class TestDjangoRouteToTemplate:
    """Tests for converting Django re_path regexes to matchable templates."""

    def test_named_group(self):
        from pytest_api_cov.frameworks import _django_route_to_template

        assert _django_route_to_template("articles/(?P<year>[0-9]{4})/") == "articles/<year>/"

    def test_unnamed_groups(self):
        from pytest_api_cov.frameworks import _django_route_to_template

        assert _django_route_to_template("files/([0-9]+)/([a-z]+)/") == "files/<param1>/<param2>/"

    def test_escaped_literals_are_unescaped(self):
        from pytest_api_cov.frameworks import _django_route_to_template

        assert _django_route_to_template(r"feed\.json") == "feed.json"

    def test_character_class_containing_parens(self):
        from pytest_api_cov.frameworks import _django_route_to_template

        assert _django_route_to_template(r"tags/(?P<tag>[()a-z]+)/") == "tags/<tag>/"

    def test_nested_groups_consume_whole_group(self):
        from pytest_api_cov.frameworks import _django_route_to_template

        assert _django_route_to_template(r"v/(?P<ver>v(1|2))/") == "v/<ver>/"

    def test_path_route_passes_through(self):
        from pytest_api_cov.frameworks import _django_route_to_template

        assert _django_route_to_template("articles/<int:year>/") == "articles/<int:year>/"

    def test_negated_class_containing_slash_stays_single_segment(self):
        from pytest_api_cov.frameworks import _django_route_to_template

        assert _django_route_to_template("x/(?P<a>[^/]+)/") == "x/<a>/"

    def test_top_level_alternation_becomes_placeholder(self):
        from pytest_api_cov.frameworks import _django_route_to_template

        assert _django_route_to_template("legacy|new") == "<param1>"

    def test_bounded_repeat_becomes_placeholder(self):
        from pytest_api_cov.frameworks import _django_route_to_template

        assert _django_route_to_template("a{2,4}/end/") == "<param1>/end/"

    def test_unparseable_route_passes_through(self):
        from pytest_api_cov.frameworks import _django_route_to_template

        assert _django_route_to_template("bad[route") == "bad[route"

    def test_shorthand_class_outside_group_becomes_placeholder(self):
        from pytest_api_cov.frameworks import _django_route_to_template

        assert _django_route_to_template(r"v\d+/users/") == "v<param1>/users/"

    def test_bare_character_class_becomes_placeholder(self):
        from pytest_api_cov.frameworks import _django_route_to_template

        assert _django_route_to_template("v[0-9]+/users/") == "v<param1>/users/"

    def test_multi_segment_group_gets_path_converter(self):
        from pytest_api_cov.frameworks import _django_route_to_template

        assert _django_route_to_template("files/(?P<rest>.*)") == "files/<path:rest>"

    def test_trailing_optional_slash_quantifier_is_dropped(self):
        from pytest_api_cov.frameworks import _django_route_to_template

        assert _django_route_to_template(r"articles/(?P<slug>[\w-]+)/?") == "articles/<slug>/"

    def test_failed_framework_import_is_probed_only_once(self, monkeypatch):
        import pytest_api_cov.frameworks as frameworks

        calls = []

        def counting_import(name, *args, **kwargs):
            calls.append(name)
            raise ImportError(name)

        monkeypatch.setattr(frameworks.importlib, "import_module", counting_import)
        monkeypatch.setattr(frameworks, "_import_failed", set())

        assert frameworks._optional_class("not_a_real_framework_xyz", "App") is None
        assert frameworks._optional_class("not_a_real_framework_xyz", "App") is None
        assert calls.count("not_a_real_framework_xyz") == 1

    def test_optional_class_resolves_current_module_object(self):
        import sys

        from pytest_api_cov.frameworks import _optional_class

        flask_class = _optional_class("flask", "Flask")
        assert flask_class is sys.modules["flask"].Flask
