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

        def test_root(client):
            client.get("/")

        def test_uncovered(client):
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
