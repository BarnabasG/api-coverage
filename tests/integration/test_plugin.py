"""Integration tests for the pytest plugin."""

pytest_plugins = ["pytester"]


def test_plugin_end_to_end(pytester):
    """An integration test for the pytest plugin using the pytester fixture."""
    pytester.makepyfile(
        """
        from flask import Flask
        import pytest

        @pytest.fixture
        def app():
            app = Flask(__name__)

            @app.route("/")
            def root():
                return "Hello"

            @app.route("/items")
            def items():
                return "Items"

            return app

        def test_root(coverage_client):
            coverage_client.get("/")

        def test_uncovered(coverage_client):
            # This test calls no endpoints
            pass
    """
    )

    result = pytester.runpytest(
        "--api-cov-report",
        "--api-cov-fail-under=90",
        "--api-cov-show-covered-endpoints",
    )

    assert result.ret == 1

    output = result.stdout.str()
    assert "API Coverage Report" in output
    assert "FAIL: Required coverage of 90.0% not met" in output
    assert "Actual coverage: 50.0%" in output
    assert "Covered Endpoints" in output
    assert "[.] /" in output
    assert "Uncovered Endpoints" in output
    assert "[X] /items" in output


def test_plugin_disabled_by_default(pytester):
    """Ensure the plugin does nothing if the flag is not provided."""
    pytester.makepyfile(
        """
        def test_simple():
            assert True
        """
    )
    result = pytester.runpytest()
    assert result.ret == 0
    assert "API Coverage Report" not in result.stdout.str()


def test_custom_fixture_wrapping_flask(pytester):
    """Test wrapping an existing custom fixture with Flask."""
    pytester.makepyfile(
        """
        from flask import Flask
        import pytest

        @pytest.fixture
        def app():
            app = Flask(__name__)

            @app.route("/")
            def root():
                return "Hello"

            @app.route("/items")
            def items():
                return "Items"

            return app

        @pytest.fixture
        def my_custom_client(app):
            client = app.test_client()
            # Add some custom setup
            client.environ_base['HTTP_AUTHORIZATION'] = 'Bearer test-token'
            return client

        def test_with_custom_client(coverage_client):
            response = coverage_client.get("/")
            assert response.status_code == 200
            assert response.data == b"Hello"
    """
    )

    result = pytester.runpytest(
        "--api-cov-report",
        "--api-cov-client-fixture-name=my_custom_client",
        "--api-cov-show-covered-endpoints",
    )

    assert result.ret == 0
    output = result.stdout.str()
    assert "API Coverage Report" in output
    assert "Total API Coverage: 50.0%" in output
    assert "Covered Endpoints" in output
    assert "[.] /" in output
    assert "Uncovered Endpoints" in output
    assert "[X] /items" in output


def test_custom_fixture_wrapping_fastapi(pytester):
    """Test wrapping an existing custom fixture with FastAPI."""
    pytester.makepyfile(
        """
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import pytest

        @pytest.fixture
        def app():
            app = FastAPI()

            @app.get("/")
            def root():
                return {"message": "Hello"}

            @app.get("/users/{user_id}")
            def get_user(user_id: int):
                return {"user_id": user_id}

            return app

        @pytest.fixture
        def my_api_client(app):
            client = TestClient(app)
            # Add some custom setup
            client.headers.update({"Authorization": "Bearer test-token"})
            return client

        def test_with_custom_client(coverage_client):
            response = coverage_client.get("/")
            assert response.status_code == 200
            assert response.json() == {"message": "Hello"}
    """
    )

    result = pytester.runpytest(
        "--api-cov-report",
        "--api-cov-client-fixture-name=my_api_client",
        "--api-cov-show-covered-endpoints",
    )

    assert result.ret == 0
    output = result.stdout.str()
    assert "API Coverage Report" in output
    assert "Total API Coverage: 50.0%" in output
    assert "Covered Endpoints" in output
    assert "[.] /" in output
    assert "Uncovered Endpoints" in output
    assert "[X] /users/{user_id}" in output


def test_custom_fixture_fallback_when_not_found(pytester):
    """Test fallback to auto-discovery when custom fixture is not found."""
    pytester.makepyfile(
        """
        from flask import Flask
        import pytest

        @pytest.fixture
        def app():
            app = Flask(__name__)

            @app.route("/")
            def root():
                return "Hello"

            return app

        def test_root(coverage_client):
            coverage_client.get("/")
    """
    )

    result = pytester.runpytest(
        "--api-cov-report",
        "--api-cov-client-fixture-name=nonexistent_fixture",
    )

    assert result.ret == 0
    output = result.stdout.str()
    assert "API Coverage Report" in output
    assert "Total API Coverage: 100.0%" in output
