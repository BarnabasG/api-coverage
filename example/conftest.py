"""example/conftest.py"""

import pytest

from example.src.main import app as fastapi_app


@pytest.fixture
def app():
    """FastAPI app fixture for testing."""
    return fastapi_app