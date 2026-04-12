"""Integration tests for FastAPI mounted sub-app route discovery."""

pytest_plugins = ["pytester"]


def test_fastapi_with_mounted_wsgi_flask_app(pytester):
    """Test that routes from a Flask app mounted via WSGIMiddleware are discovered."""
    pytester.makepyfile(
        """
        from fastapi import FastAPI
        from fastapi.middleware.wsgi import WSGIMiddleware
        from flask import Flask
        import pytest

        flask_app = Flask(__name__)

        @flask_app.route("/hello")
        def flask_hello():
            return "Hello from Flask"

        fastapi_app = FastAPI()

        @fastapi_app.get("/")
        def fastapi_root():
            return {"message": "Hello from FastAPI"}

        fastapi_app.mount("/flask", WSGIMiddleware(flask_app))

        @pytest.fixture
        def app():
            return fastapi_app

        def test_root(coverage_client):
            response = coverage_client.get("/")
            assert response.status_code == 200

        def test_flask_hello(coverage_client):
            response = coverage_client.get("/flask/hello")
            assert response.status_code == 200
    """
    )

    result = pytester.runpytest(
        "--api-cov-report",
        "--api-cov-show-covered-endpoints",
        "--api-cov-force-sugar-disabled",
    )

    assert result.ret == 0
    output = result.stdout.str()
    assert "API Coverage Report" in output
    # FastAPI route should be discovered
    assert "GET    /" in output
    # Flask mounted route should also be discovered with prefix
    assert "GET    /flask/hello" in output


def test_fastapi_with_mounted_sub_app(pytester):
    """Test that routes from a mounted FastAPI sub-app are discovered."""
    pytester.makepyfile(
        """
        from fastapi import FastAPI
        import pytest

        sub_app = FastAPI()

        @sub_app.get("/users")
        def list_users():
            return [{"id": 1}]

        @sub_app.get("/users/{user_id}")
        def get_user(user_id: int):
            return {"id": user_id}

        main_app = FastAPI()

        @main_app.get("/")
        def root():
            return {"message": "Hello"}

        main_app.mount("/api/v2", sub_app)

        @pytest.fixture
        def app():
            return main_app

        def test_root(coverage_client):
            response = coverage_client.get("/")
            assert response.status_code == 200

        def test_list_users(coverage_client):
            response = coverage_client.get("/api/v2/users")
            assert response.status_code == 200
    """
    )

    result = pytester.runpytest(
        "--api-cov-report",
        "--api-cov-show-covered-endpoints",
        "--api-cov-force-sugar-disabled",
    )

    assert result.ret == 0
    output = result.stdout.str()
    assert "API Coverage Report" in output
    # Main app route
    assert "GET    /" in output
    # Sub-app routes should be discovered with prefix
    assert "GET    /api/v2/users" in output
    assert "GET    /api/v2/users/{user_id}" in output
