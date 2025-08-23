"""example/tests/test_endpoints.py"""


def test_root_path(client):
    """Test the root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello World"}


def test_items_path(client):
    """Test the items endpoint."""
    response = client.get("/items/42")
    assert response.status_code == 200
    assert response.json() == {"item_id": 42}


def test_xyz_and_root_path(client):
    """Test the xyz endpoint."""
    response = client.get("/xyz/123")
    assert response.status_code == 404
    response = client.get("/xyzzyx")
    assert response.status_code == 200
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello World"}
