"""example/tests/test_endpoints.py"""


def test_root_path(coverage_client):
    """Test the root endpoint."""
    response = coverage_client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello World"}


def test_items_path(coverage_client):
    """Test the items endpoint."""
    response = coverage_client.get("/items/42")
    assert response.status_code == 200
    assert response.json() == {"item_id": 42}


def test_create_item(coverage_client):
    """Test creating an item."""
    response = coverage_client.post("/items", json={"name": "test item"})
    assert response.status_code == 200
    assert response.json()["message"] == "Item created"


def test_xyz_and_root_path(coverage_client):
    """Test the xyz endpoint."""
    response = coverage_client.get("/xyz/123")
    assert response.status_code == 404
    response = coverage_client.get("/xyzzyx")
    assert response.status_code == 200
    response = coverage_client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello World"}
