"""Integration tests for framework adapters."""

import pytest

from pytest_api_cov.frameworks import FastAPIAdapter, FlaskAdapter
from pytest_api_cov.models import ApiCallRecorder


class TestFlaskIntegration:
    """Integration tests for Flask framework adapter."""

    def test_flask_tracking_integration(self):
        """Test with a real Flask app."""
        try:
            from flask import Flask

            app = Flask(__name__)

            @app.route("/")
            def root():
                return "Hello"

            @app.route("/users/<user_id>")
            def user(user_id):
                return f"User {user_id}"

            @app.route("/items")
            def items():
                return "Items"

            adapter = FlaskAdapter(app)

            endpoints = adapter.get_endpoints()
            assert "/" in endpoints
            assert "/users/<user_id>" in endpoints
            assert "/items" in endpoints

            recorder = ApiCallRecorder()
            client = adapter.get_tracked_client(recorder, "test_flask_tracking")

            response = client.open("/")
            assert response.status_code == 200

            response = client.open("/users/123")
            assert response.status_code == 200

            response = client.open("/items")
            assert response.status_code == 200

            assert "/" in recorder
            assert "/users/<user_id>" in recorder
            assert "/items" in recorder
            assert "test_flask_tracking" in recorder.get_callers("/")
            assert "test_flask_tracking" in recorder.get_callers("/users/<user_id>")
            assert "test_flask_tracking" in recorder.get_callers("/items")

        except ImportError:
            pytest.skip("Flask not available for integration testing")

    def test_flask_excluded_endpoints(self):
        """Test that static endpoints are excluded."""
        try:
            from flask import Flask

            app = Flask(__name__)

            @app.route("/static/<path:filename>")
            def static_file(filename):
                return f"Static {filename}"

            @app.route("/api/users")
            def api_users():
                return "API Users"

            adapter = FlaskAdapter(app)
            endpoints = adapter.get_endpoints()

            assert "/static/<path:filename>" not in endpoints
            assert "/api/users" in endpoints

        except ImportError:
            pytest.skip("Flask not available for integration testing")


class TestFastAPIIntegration:
    """Integration tests for FastAPI framework adapter."""

    def test_fastapi_tracking_integration(self):
        """Test with a real FastAPI app."""
        try:
            from fastapi import FastAPI

            app = FastAPI()

            @app.get("/")
            def root():
                return "Hello"

            @app.get("/users/{user_id}")
            def user(user_id: int):
                return f"User {user_id}"

            @app.post("/items")
            def create_item():
                return "Item created"

            adapter = FastAPIAdapter(app)

            endpoints = adapter.get_endpoints()
            assert "/" in endpoints
            assert "/users/{user_id}" in endpoints
            assert "/items" in endpoints

            recorder = ApiCallRecorder()
            client = adapter.get_tracked_client(recorder, "test_fastapi_tracking")

            response = client.get("/")
            assert response.status_code == 200

            response = client.get("/users/123")
            assert response.status_code == 200

            response = client.post("/items")
            assert response.status_code == 200

            assert "/" in recorder
            assert "/items" in recorder
            assert "test_fastapi_tracking" in recorder.get_callers("/")
            assert "test_fastapi_tracking" in recorder.get_callers("/items")

            user_paths = [k for k in recorder.keys() if k.startswith("/users/")]
            assert len(user_paths) > 0
            assert "test_fastapi_tracking" in recorder.get_callers(user_paths[0])

        except ImportError:
            pytest.skip("FastAPI not available for integration testing")

    def test_fastapi_route_filtering(self):
        """Test that only APIRoute instances are included."""
        try:
            import tempfile

            from fastapi import FastAPI
            from fastapi.staticfiles import StaticFiles

            app = FastAPI()

            @app.get("/api/users")
            def api_users():
                return "API Users"

            with tempfile.TemporaryDirectory() as temp_dir:
                app.mount("/static", StaticFiles(directory=temp_dir), name="static")

                adapter = FastAPIAdapter(app)
                endpoints = adapter.get_endpoints()

                assert "/api/users" in endpoints
                assert "/static" not in endpoints

        except ImportError:
            pytest.skip("FastAPI not available for integration testing")
