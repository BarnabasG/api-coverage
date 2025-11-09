"""example/conftest.py"""

import pytest
from fastapi.testclient import TestClient

from example.src.main import app as fastapi_app


@pytest.fixture
def client():
    """Standard FastAPI test client fixture.

    The pytest-api-cov plugin will automatically discover this fixture,
    extract the app from it, and wrap it with coverage tracking.
    """
    return TestClient(fastapi_app)
