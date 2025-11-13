"""example/conftest.py"""

import pytest
from fastapi.testclient import TestClient

from example.src.main import app as fastapi_app
from pytest_api_cov.plugin import create_coverage_fixture


@pytest.fixture
def original_client():
    """Original FastAPI test client fixture.

    This fixture demonstrates an existing user-provided client that we can wrap
    with `create_coverage_fixture` so tests can continue to use the familiar
    `client` fixture name while gaining API coverage tracking.
    """
    return TestClient(fastapi_app)


# Create a wrapped fixture named 'client' that wraps the existing 'original_client'.
# Tests can continue to request the `client` fixture as before and coverage will be
# collected when pytest is run with --api-cov-report.
client = create_coverage_fixture("client", "original_client")
