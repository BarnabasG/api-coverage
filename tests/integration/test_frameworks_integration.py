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
            assert "GET /" in endpoints
            assert "GET /users/<user_id>" in endpoints
            assert "GET /items" in endpoints

            recorder = ApiCallRecorder()
            client = adapter.get_tracked_client(recorder, "test_flask_tracking")

            response = client.open("/")
            assert response.status_code == 200

            response = client.open("/users/123")
            assert response.status_code == 200

            response = client.open("/items")
            assert response.status_code == 200

            assert "GET /" in recorder
            assert "GET /users/<user_id>" in recorder
            assert "GET /items" in recorder
            assert "test_flask_tracking" in recorder.calls["GET /"]
            assert "test_flask_tracking" in recorder.calls["GET /users/<user_id>"]
            assert "test_flask_tracking" in recorder.calls["GET /items"]

        except ImportError:
            pytest.skip("Flask not available for integration testing")

    def test_flask_excluded_endpoints(self):
        """Framework static routes are excluded by endpoint name; user routes are kept."""
        try:
            from flask import Blueprint, Flask

            app = Flask(__name__, static_url_path="/assets")

            @app.route("/api/users")
            def api_users():
                return "API Users"

            blueprint = Blueprint("admin", __name__, static_folder="static", url_prefix="/admin")
            app.register_blueprint(blueprint)

            adapter = FlaskAdapter(app)
            endpoints = adapter.get_endpoints()
            paths = [ep.split(" ", 1)[1] if " " in ep else ep for ep in endpoints]

            assert "/assets/<path:filename>" not in paths
            assert "/admin/static/<path:filename>" not in paths
            assert "GET /api/users" in endpoints

        except ImportError:
            pytest.skip("Flask not available for integration testing")

    def test_flask_user_route_shadowing_static_path_is_kept(self):
        """A user view routed under /static/ is a real endpoint and must be counted."""
        try:
            from flask import Flask

            app = Flask(__name__)

            @app.route("/static/<path:filename>")
            def static_file(filename):
                return f"Static {filename}"

            adapter = FlaskAdapter(app)
            endpoints = adapter.get_endpoints()

            assert "GET /static/<path:filename>" in endpoints

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
            assert "GET /" in endpoints
            assert "GET /users/{user_id}" in endpoints
            assert "POST /items" in endpoints

            recorder = ApiCallRecorder()
            client = adapter.get_tracked_client(recorder, "test_fastapi_tracking")

            response = client.get("/")
            assert response.status_code == 200

            response = client.get("/users/123")
            assert response.status_code == 200

            response = client.post("/items")
            assert response.status_code == 200

            assert "GET /" in recorder
            assert "POST /items" in recorder
            assert "test_fastapi_tracking" in recorder.calls["GET /"]
            assert "test_fastapi_tracking" in recorder.calls["POST /items"]

            user_paths = [k for k in recorder.keys() if k.startswith("GET /users/")]
            assert len(user_paths) > 0
            assert "test_fastapi_tracking" in recorder.calls[user_paths[0]]

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

                assert "GET /api/users" in endpoints
                assert "/static" not in endpoints

        except ImportError:
            pytest.skip("FastAPI not available for integration testing")


class TestFlaskTrackingRegressions:
    """Regression tests for Flask tracked-client recording."""

    @staticmethod
    def _make_adapter_and_recorder():
        from flask import Flask

        app = Flask(__name__)

        @app.route("/items")
        def items():
            return "Items"

        @app.route("/slash/")
        def slash():
            return "Slash"

        @app.route("/a")
        @app.route("/b")
        def multi():
            return "Multi"

        return FlaskAdapter(app), ApiCallRecorder()

    def test_query_string_calls_are_recorded(self):
        """A request with a query string still records the matched rule."""
        try:
            adapter, recorder = self._make_adapter_and_recorder()
        except ImportError:
            pytest.skip("Flask not available for integration testing")

        client = adapter.get_tracked_client(recorder, "test_query")
        response = client.get("/items?page=2&size=10")

        assert response.status_code == 200
        assert "GET /items" in recorder

    def test_multi_decorated_view_records_the_called_rule(self):
        """With two route decorators on one view, the rule actually called is recorded."""
        try:
            adapter, recorder = self._make_adapter_and_recorder()
        except ImportError:
            pytest.skip("Flask not available for integration testing")

        client = adapter.get_tracked_client(recorder, "test_multi")
        client.get("/a")

        assert "GET /a" in recorder
        assert "GET /b" not in recorder

        client.get("/b")
        assert "GET /b" in recorder

    def test_followed_trailing_slash_redirect_is_recorded(self):
        """/slash -> /slash/ with follow_redirects=True reaches the view and is recorded."""
        try:
            adapter, recorder = self._make_adapter_and_recorder()
        except ImportError:
            pytest.skip("Flask not available for integration testing")

        client = adapter.get_tracked_client(recorder, "test_redirect")
        response = client.get("/slash", follow_redirects=True)

        assert response.status_code == 200
        assert "GET /slash/" in recorder

    def test_unfollowed_redirect_is_not_recorded(self):
        """Without follow_redirects the view never runs, so nothing is recorded."""
        try:
            adapter, recorder = self._make_adapter_and_recorder()
        except ImportError:
            pytest.skip("Flask not available for integration testing")

        client = adapter.get_tracked_client(recorder, "test_no_follow")
        response = client.get("/slash")

        assert response.status_code in (301, 308)
        assert len(recorder) == 0


class TestFrameworkSubclassDetection:
    """Apps subclassing Flask/FastAPI must be detected."""

    def test_flask_subclass_is_detected(self):
        """A Flask subclass resolves to the Flask adapter."""
        try:
            from flask import Flask
        except ImportError:
            pytest.skip("Flask not available for integration testing")

        from pytest_api_cov.frameworks import get_framework_adapter

        class CustomFlask(Flask):
            pass

        assert isinstance(get_framework_adapter(CustomFlask(__name__)), FlaskAdapter)

    def test_fastapi_subclass_is_detected(self):
        """A FastAPI subclass resolves to the FastAPI adapter."""
        try:
            from fastapi import FastAPI
        except ImportError:
            pytest.skip("FastAPI not available for integration testing")

        from pytest_api_cov.frameworks import get_framework_adapter

        class CustomFastAPI(FastAPI):
            pass

        assert isinstance(get_framework_adapter(CustomFastAPI()), FastAPIAdapter)


class TestFastAPIRouteDiscoveryRegressions:
    """Regression tests for FastAPI/Starlette route discovery and recording."""

    def test_plain_starlette_routes_are_discovered_but_docs_are_not(self):
        """add_route() endpoints appear; auto-generated docs routes do not."""
        try:
            from fastapi import FastAPI
            from starlette.responses import PlainTextResponse
        except ImportError:
            pytest.skip("FastAPI not available for integration testing")

        app = FastAPI()

        async def plain(request):
            return PlainTextResponse("ok")

        app.add_route("/plain", plain, methods=["GET"])

        endpoints = FastAPIAdapter(app).get_endpoints()

        assert "GET /plain" in endpoints
        assert not any("/docs" in ep or "/openapi.json" in ep or "/redoc" in ep for ep in endpoints)

    def test_mounted_starlette_app_routes_are_discovered(self):
        """Routes of a mounted plain Starlette app appear with the mount prefix."""
        try:
            from fastapi import FastAPI
            from starlette.applications import Starlette
            from starlette.responses import PlainTextResponse
            from starlette.routing import Route
        except ImportError:
            pytest.skip("FastAPI not available for integration testing")

        async def sub(request):
            return PlainTextResponse("sub")

        subapp = Starlette(routes=[Route("/sub", sub, methods=["GET"])])
        app = FastAPI()
        app.mount("/mnt", subapp)

        endpoints = FastAPIAdapter(app).get_endpoints()

        assert "GET /mnt/sub" in endpoints

    def test_followed_slash_redirect_records_final_path(self):
        """/items redirected to /items/ records the real route path, not the original."""
        try:
            from fastapi import FastAPI
        except ImportError:
            pytest.skip("FastAPI not available for integration testing")

        app = FastAPI()

        @app.get("/items/")
        def items():
            return {"ok": True}

        recorder = ApiCallRecorder()
        client = FastAPIAdapter(app).get_tracked_client(recorder, "test_redirect")

        response = client.get("/items", follow_redirects=True)

        assert response.status_code == 200
        assert "GET /items/" in recorder
        assert "GET /items" not in recorder
