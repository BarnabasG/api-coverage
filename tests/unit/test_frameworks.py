"""Tests for framework adapters."""

from unittest.mock import Mock, patch

import pytest

from pytest_api_cov.frameworks import FastAPIAdapter, FlaskAdapter, get_framework_adapter


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
    """Tests for the Flask framework adapter."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_app = Mock()
        self.mock_app.__module__ = "flask"
        type(self.mock_app).__name__ = "Flask"
        self.mock_app.url_map = MockFlaskURLMap()
        self.adapter = FlaskAdapter(self.mock_app)

    def test_flask_get_endpoints(self):
        """Verify endpoint discovery for Flask."""
        endpoints = self.adapter.get_endpoints()
        expected = ["GET /", "GET /users/<id>", "POST /", "POST /users/<id>"]
        assert sorted(endpoints) == sorted(expected)

    def test_flask_get_tracked_client_no_recorder(self):
        """Test that get_tracked_client returns normal client when recorder is None."""
        client = self.adapter.get_tracked_client(None, "test_name")
        assert client == self.mock_app.test_client()

    def test_flask_get_tracked_client_with_recorder(self):
        """Test that get_tracked_client returns tracking client when recorder is provided."""
        self.mock_app.response_class = type("MockResponse", (), {})

        recorder = {}
        client = self.adapter.get_tracked_client(recorder, "test_name")
        assert hasattr(client, "open")
        assert "TrackingFlaskClient" in str(type(client))

    def test_flask_tracking_client_open_method(self):
        """Test the TrackingFlaskClient open method."""
        with patch("flask.testing.FlaskClient"):
            recorder = {}
            client = self.adapter.get_tracked_client(recorder, "test_name")

            client.open = Mock(return_value="response")

            response = client.open(path="/test", method="GET")
            assert response == "response"

            response = client.open("/test2", method="POST")
            assert response == "response"

    def test_flask_tracking_client_exception_handling(self):
        """Test exception handling in Flask tracking client."""
        from unittest.mock import Mock, patch

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
    """Tests for the FastAPI framework adapter."""

    def setup_method(self):
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
        """Verify endpoint discovery for FastAPI."""
        with patch("fastapi.routing.APIRoute", MockFastAPIRoute):
            endpoints = self.adapter.get_endpoints()
            expected = ["GET /", "GET /items/{item_id}", "POST /", "POST /items/{item_id}"]
            assert sorted(endpoints) == sorted(expected)

    def test_fastapi_get_tracked_client_no_recorder(self):
        """Test that get_tracked_client returns normal client when recorder is None."""
        with patch("starlette.testclient.TestClient") as MockTestClient:
            self.adapter.get_tracked_client(None, "test_name")
            MockTestClient.assert_called_once_with(self.mock_app)

    def test_fastapi_get_tracked_client_with_recorder(self):
        """Test that get_tracked_client returns tracking client when recorder is provided."""
        recorder = {}
        client = self.adapter.get_tracked_client(recorder, "test_name")
        assert hasattr(client, "send")
        assert "TrackingFastAPIClient" in str(type(client))

    def test_fastapi_tracking_client_send_method(self):
        """Test the TrackingFastAPIClient send method exists and can be called."""
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
    """Test the base adapter class."""

    def test_base_adapter_get_endpoints_not_implemented(self):
        """Test that BaseAdapter.get_endpoints raises NotImplementedError."""
        from pytest_api_cov.frameworks import BaseAdapter

        base_adapter = BaseAdapter(None)
        with pytest.raises(NotImplementedError):
            base_adapter.get_endpoints()

    def test_base_adapter_get_tracked_client_not_implemented(self):
        """Test that BaseAdapter.get_tracked_client raises NotImplementedError."""
        from pytest_api_cov.frameworks import BaseAdapter

        base_adapter = BaseAdapter(None)
        with pytest.raises(NotImplementedError):
            base_adapter.get_tracked_client({}, "test")


class TestAdapterFactory:
    """Tests the factory function for getting adapters."""

    def test_get_framework_adapter(self):
        """Test the factory function for selecting the correct adapter."""

        class MockFlask:
            __module__ = "flask.app"
            __name__ = "Flask"

        class MockFastAPI:
            __module__ = "fastapi.applications"
            __name__ = "FastAPI"

        class MockWSGIHandler:
            __module__ = "django.core.handlers.wsgi"
            __name__ = "WSGIHandler"

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

        # Django is now supported
        from pytest_api_cov.frameworks import DjangoAdapter

        assert isinstance(get_framework_adapter(mock_django_app), DjangoAdapter)

        with pytest.raises(TypeError, match="Unsupported application type"):
            get_framework_adapter(mock_unsupported_app)

    def test_get_framework_adapter_with_missing_module(self):
        """Test factory function with app that has no __module__ attribute."""
        mock_app = Mock()
        mock_class = Mock()
        mock_class.__name__ = "UnknownApp"
        del mock_class.__module__
        mock_app.__class__ = mock_class

        with pytest.raises(TypeError, match="Unsupported application type"):
            get_framework_adapter(mock_app)
