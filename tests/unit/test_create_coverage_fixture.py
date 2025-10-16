"""Unit tests for create_coverage_fixture function."""

from src.pytest_api_cov.plugin import create_coverage_fixture


class TestCreateCoverageFixture:
    """Tests for the create_coverage_fixture helper function."""

    def test_create_coverage_fixture_returns_callable(self):
        """Test that create_coverage_fixture returns a callable fixture function."""
        fixture_func = create_coverage_fixture("test_client")

        assert callable(fixture_func)
        assert fixture_func.__name__ == "test_client"

    def test_create_coverage_fixture_with_existing_fixture_name(self):
        """Test create_coverage_fixture with existing fixture name parameter."""
        fixture_func = create_coverage_fixture("my_client", "existing_client")

        assert callable(fixture_func)
        assert fixture_func.__name__ == "my_client"

    def test_create_coverage_fixture_is_pytest_fixture(self):
        """Test that the created function is a pytest fixture."""
        fixture_func = create_coverage_fixture("test_client")

        # Should be a pytest fixture (has _pytestfixturefunction or similar attribute)
        assert hasattr(fixture_func, "_pytestfixturefunction") or hasattr(fixture_func, "_fixture_function")

    def test_create_coverage_fixture_preserves_name(self):
        """Test that the fixture function preserves the specified name."""
        fixture_func = create_coverage_fixture("custom_name")

        # The function name should be preserved
        assert fixture_func.__name__ == "custom_name"
