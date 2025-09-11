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
    assert "[.] GET" in output
    assert "Uncovered Endpoints" in output
    assert "[X] GET" in output


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
    assert "[.] GET" in output
    assert "Uncovered Endpoints" in output
    assert "[X] GET" in output


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
    assert "[.] GET" in output
    assert "Uncovered Endpoints" in output
    assert "[X] GET" in output


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


def test_custom_app_location_via_fixture(pytester):
    """Test that apps can be imported from any custom location via app fixture."""
    # Create a nested directory structure
    pytester.makepyfile(
        **{
            "my_project/backend/server.py": """
                from flask import Flask

                my_custom_app = Flask(__name__)

                @my_custom_app.route("/")
                def root():
                    return "Hello from custom location"

                @my_custom_app.route("/api/users")
                def users():
                    return "Users endpoint"
            """,
            "my_project/__init__.py": "",
            "my_project/backend/__init__.py": "",
            "conftest.py": """
                import pytest
                from my_project.backend.server import my_custom_app

                @pytest.fixture
                def app():
                    return my_custom_app
            """,
            "test_custom_location.py": """
                def test_root_endpoint(coverage_client):
                    response = coverage_client.get("/")
                    assert response.status_code == 200
                    assert response.data == b"Hello from custom location"
            """,
        }
    )

    result = pytester.runpytest(
        "--api-cov-report",
        "--api-cov-show-covered-endpoints",
    )

    assert result.ret == 0
    output = result.stdout.str()
    assert "API Coverage Report" in output
    assert "Total API Coverage: 50.0%" in output
    assert "Covered Endpoints" in output
    assert "[.] GET" in output
    assert "Uncovered Endpoints" in output
    assert "[X] GET" in output


def test_multiple_auto_discover_files_uses_first(pytester):
    """Test that when multiple auto-discover files exist, the first valid one is used."""
    pytester.makepyfile(
        **{
            "app.py": """
                from flask import Flask
                app = Flask(__name__)

                @app.route("/from-app-py")
                def from_app():
                    return "From app.py"
            """,
            "main.py": """
                from flask import Flask
                app = Flask(__name__)

                @app.route("/from-main-py")
                def from_main():
                    return "From main.py"
            """,
            "test_multiple.py": """
                def test_endpoint(coverage_client):
                    # Should use app.py since it comes first in the pattern list
                    response = coverage_client.get("/from-app-py")
                    assert response.status_code == 200
            """,
        }
    )

    result = pytester.runpytest("--api-cov-report", "-v")

    assert result.ret == 0
    output = result.stdout.str()
    assert "API Coverage Report" in output
    assert "Total API Coverage: 100.0%" in output
    # The test should pass, meaning it used app.py (first in priority order)


def test_override_auto_discovery_with_fixture(pytester):
    """Test that app fixture overrides auto-discovery."""
    pytester.makepyfile(
        **{
            "app.py": """
                from flask import Flask
                wrong_app = Flask(__name__)

                @wrong_app.route("/wrong")
                def wrong():
                    return "Wrong app"
            """,
            "my_real_app.py": """
                from flask import Flask
                real_app = Flask(__name__)

                @real_app.route("/correct")
                def correct():
                    return "Correct app"
            """,
            "conftest.py": """
                import pytest
                from my_real_app import real_app

                @pytest.fixture
                def app():
                    return real_app
            """,
            "test_override.py": """
                def test_correct_app(coverage_client):
                    # Should use the app from fixture, not auto-discovery
                    response = coverage_client.get("/correct")
                    assert response.status_code == 200
            """,
        }
    )

    result = pytester.runpytest("--api-cov-report")

    assert result.ret == 0
    output = result.stdout.str()
    assert "API Coverage Report" in output
    assert "Total API Coverage: 100.0%" in output
    # The test should pass, meaning it used the correct app from fixture
    # (if it used auto-discovery, it would try to access /wrong and fail)


def test_auto_discover_file_exists_but_wrong_variable_name(pytester):
    """Test when auto-discover file exists but app has different variable name."""
    pytester.makepyfile(
        **{
            "app.py": """
                from flask import Flask
                my_custom_app_name = Flask(__name__)

                @my_custom_app_name.route("/")
                def root():
                    return "Hello"
            """,
            "conftest.py": """
                import pytest
                from app import my_custom_app_name

                @pytest.fixture
                def app():
                    return my_custom_app_name
            """,
            "test_custom_name.py": """
                def test_endpoint(coverage_client):
                    response = coverage_client.get("/")
                    assert response.status_code == 200
            """,
        }
    )

    result = pytester.runpytest("--api-cov-report")

    assert result.ret == 0
    output = result.stdout.str()
    assert "API Coverage Report" in output
    assert "Total API Coverage: 100.0%" in output
    # The test should pass, meaning it used the app fixture with custom variable name
