# tests/integration/test_plugin.py

pytest_plugins = ["pytester"]


def test_plugin_end_to_end(pytester):
    """
    An integration test for the pytest plugin using the pytester fixture.
    """
    # 1. Create a dummy Flask app and tests
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

    # 2. Run pytest with the api-coverage flags
    result = pytester.runpytest(
        "--api-cov-report",
        "--api-cov-fail-under=90",  # Should fail
        "--api-cov-show-covered-endpoints",  # To check output
    )

    # 3. Assert on the results
    assert result.ret == 1  # The pytest session should fail due to coverage

    # 4. Check the console output for the report
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
    result = pytester.runpytest()  # No --api-cov-report flag
    assert result.ret == 0  # Should pass normally
    assert "API Coverage Report" not in result.stdout.str()
