# pytest-api-cov

A **pytest plugin** that measures **API endpoint coverage** for FastAPI and Flask applications. Know which endpoints are tested and which are missing coverage.

## Features

- **Zero Configuration**: Plug-and-play with Flask/FastAPI apps - just install and run
- **Terminal Reports**: Rich terminal output with detailed coverage information
- **JSON Reports**: Export coverage data for CI/CD integration
- **Setup Wizard**: Interactive setup wizard for complex projects

## Quick Start

### Installation

```bash
pip install pytest-api-cov
```

### Basic Usage

For most projects, no configuration is needed:

```bash
# Just add the flag to your pytest command
pytest --api-cov-report
```

### App Location Flexibility

**Zero Config**: Works automatically if your app is in `app.py`, `main.py`, or `server.py`

**Any Location**: Place your app anywhere in your project - just create a `conftest.py`:

```python
import pytest
from my_project.backend.api import my_app  # Any import path!

@pytest.fixture
def app():
    return my_app
```

The plugin will automatically discover your Flask/FastAPI app if it's in common locations:
- `app.py` (with variable `app`, `application`, or `main`)
- `main.py` (with variable `app`, `application`, or `main`) 
- `server.py` (with variable `app`, `application`, or `server`)

**Your app can be located anywhere!** If it's not in a standard location, just create a `conftest.py` file to tell the plugin where to find it.

### Example

Given this FastAPI app in `app.py`:

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello World"}

@app.get("/users/{user_id}")
def get_user(user_id: int):
    return {"user_id": user_id}

@app.post("/users")
def create_user(user: dict):
    return {"message": "User created", "user": user}

@app.get("/health")
def health_check():
    return {"status": "ok"}
```

And this test file:

```python
def test_root_endpoint(coverage_client):
    response = coverage_client.get("/")
    assert response.status_code == 200

def test_get_user(coverage_client):
    response = coverage_client.get("/users/123")
    assert response.status_code == 200

def test_create_user(coverage_client):
    response = coverage_client.post("/users", json={"name": "John"})
    assert response.status_code == 200
```

Running `pytest --api-cov-report` produces:

```
API Coverage Report
Uncovered Endpoints:
  ❌ GET    /health

Total API Coverage: 66.67%
```

Or running with advanced options:
```bash
pytest --api-cov-report --api-cov-show-covered-endpoints --api-cov-exclusion-patterns="/users*" --api-cov-show-excluded-endpoints --api-cov-report-path=api_coverage.json
```

```
API Coverage Report
Uncovered Endpoints:
  ❌ GET    /health
Covered Endpoints:
  ✅ GET    /
Excluded Endpoints:
  🚫 GET    /users/{user_id}
  🚫 POST   /users

Total API Coverage: 50.0%

JSON report saved to api_coverage.json
```

## HTTP Method-Aware Coverage

By default, pytest-api-cov tracks coverage for **each HTTP method separately**. This means `GET /users` and `POST /users` are treated as different endpoints for coverage purposes.

### Method-Aware (Default Behavior)
```
Covered Endpoints:
  ✅ GET    /users/{id}
  ✅ POST   /users
Uncovered Endpoints:
  ❌ PUT    /users/{id}
  ❌ DELETE /users/{id}

Total API Coverage: 50.0%  # 2 out of 4 method-endpoint combinations
```

### Endpoint Grouping
To group all methods by endpoint, use:

```bash
pytest --api-cov-report --api-cov-group-methods-by-endpoint
```

Or in `pyproject.toml`:
```toml
[tool.pytest_api_cov]
group_methods_by_endpoint = true
```

This would show:
```
Covered Endpoints:
  ✅ /users/{id}  # Any method tested
  ✅ /users       # Any method tested

Total API Coverage: 100.0%  # All endpoints have at least one method tested
```

## Advanced Configuration

### Setup Wizard

If auto-discovery doesn't work for your project, use the interactive setup wizard:

```bash
pytest-api-cov init
```

This will:
- Detect your framework and app location
- Create a `conftest.py` fixture if needed
- Generate suggested `pyproject.toml` configuration

### Manual Configuration

Create a `conftest.py` file to specify your app location (works with **any** file path or structure):

```python
import pytest

# Import from anywhere in your project
from my_project.backend.api import flask_app
# or from src.services.web_server import fastapi_instance  
# or from deeply.nested.modules import my_app

@pytest.fixture
def app():
    return flask_app  # Return your app instance
```

This approach works with any project structure - the plugin doesn't care where your app is located as long as you can import it.

### Custom Test Client Fixtures

If you have an existing test client fixture with custom setup (authentication, headers, etc.), you can wrap it with coverage tracking:

```python
import pytest
from fastapi.testclient import TestClient
from your_app import app

@pytest.fixture
def my_custom_client():
    """Custom test client with authentication."""
    client = TestClient(app)
    client.headers.update({"Authorization": "Bearer test-token"})
    return client

def test_endpoint(coverage_client):
    # coverage_client will be your custom client with coverage tracking
    response = coverage_client.get("/protected-endpoint")
    assert response.status_code == 200
```

Configure it in `pyproject.toml`:

```toml
[tool.pytest_api_cov]
client_fixture_name = "my_custom_client"
```

Or via command line:

```bash
pytest --api-cov-report --api-cov-client-fixture-name=my_custom_client
```

### Configuration Options

Add configuration to your `pyproject.toml`:

```toml
[tool.pytest_api_cov]
# Fail if coverage is below this percentage
fail_under = 80.0

# Control what's shown in reports
show_uncovered_endpoints = true
show_covered_endpoints = false
show_excluded_endpoints = false

# Exclude endpoints from coverage using wildcard patterns with negation support
# Use * for wildcard matching, all other characters are matched literally
# Use ! at the start to negate a pattern (include what would otherwise be excluded)
exclusion_patterns = [
    "/health",        # Exact match
    "/metrics",       # Exact match
    "/docs/*",        # Wildcard: matches /docs/swagger, /docs/openapi, etc.
    "/admin/*",       # Wildcard: matches all admin endpoints
    "!/admin/public", # Negation: include /admin/public even though /admin/* excludes it
    "/api/v1.0/*",    # Exact version match (won't match /api/v1x0/*)
    "!/api/v1.0/health" # Negation: include /api/v1.0/health even though /api/v1.0/* excludes it
]

# Save detailed JSON report
report_path = "api_coverage.json"

# Force Unicode symbols in output
force_sugar = true

# Force no Unicode symbols in output
force_sugar_disabled = true

# Wrap an existing custom test client fixture with coverage tracking
client_fixture_name = "my_custom_client"

# Group HTTP methods by endpoint for legacy behavior (default: false)
# When true: treats GET /users and POST /users as one "/users" endpoint  
# When false: treats them as separate "GET /users" and "POST /users" endpoints (recommended)
group_methods_by_endpoint = false
```

### Command Line Options

```bash
# Basic coverage report
pytest --api-cov-report

# Set coverage threshold to fail test session
pytest --api-cov-report --api-cov-fail-under=80

# Show covered endpoints
pytest --api-cov-report --api-cov-show-covered-endpoints

# Show excluded endpoints
pytest --api-cov-report --api-cov-show-excluded-endpoints

# Hide uncovered endpoints
pytest --api-cov-report --api-cov-show-uncovered-endpoints=false

# Save JSON report
pytest --api-cov-report --api-cov-report-path=api_coverage.json

# Exclude specific endpoints (supports wildcards and negation)
pytest --api-cov-report --api-cov-exclusion-patterns="/health" --api-cov-exclusion-patterns="/docs/*"

# Exclude with negation (exclude all admin except admin/public)
pytest --api-cov-report --api-cov-exclusion-patterns="/admin/*" --api-cov-exclusion-patterns="!/admin/public"

# Verbose logging (shows discovery process)
pytest --api-cov-report -v

# Debug logging (very detailed)
pytest --api-cov-report -vv

# Group HTTP methods by endpoint (legacy behavior)
pytest --api-cov-report --api-cov-group-methods-by-endpoint
```

## Framework Support

Works automatically with FastAPI and Flask applications.

### FastAPI

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/items/{item_id}")
def read_item(item_id: int):
    return {"item_id": item_id}

# Tests automatically get a 'coverage_client' fixture
def test_read_item(coverage_client):
    response = coverage_client.get("/items/42")
    assert response.status_code == 200
```

### Flask

```python
from flask import Flask

app = Flask(__name__)

@app.route("/users/<int:user_id>")
def get_user(user_id):
    return {"user_id": user_id}

# Tests automatically get a 'coverage_client' fixture  
def test_get_user(coverage_client):
    response = coverage_client.get("/users/123")
    assert response.status_code == 200
```

## Parallel Testing

pytest-api-cov fully supports pytest-xdist for parallel test execution:

```bash
# Run tests in parallel with coverage
pytest --api-cov-report -n auto
```

Coverage data is automatically collected from all worker processes and merged in the final report.

## JSON Report Format

When using `--api-cov-report-path`, the plugin generates a detailed JSON report:

```json
{
  "status": 0,
  "coverage": 66.67,
  "required_coverage": 80.0,
  "total_endpoints": 3,
  "covered_count": 2,
  "uncovered_count": 1,
  "excluded_count": 0,
  "detail": [
    {
      "endpoint": "/",
      "callers": ["test_root_endpoint"]
    },
    {
      "endpoint": "/users/{user_id}",
      "callers": ["test_get_user"]
    },
    {
      "endpoint": "/health",
      "callers": []
    }
  ]
}
```

## CI/CD Integration

### Fail on Low Coverage

```bash
# Fail the build if coverage is below 80%
pytest --api-cov-report --api-cov-fail-under=80
```

### GitHub Actions Example

```yaml
name: API Coverage
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v4
      with:
        python-version: '3.12'
    - run: pip install pytest pytest-api-cov
    - run: pytest --api-cov-report --api-cov-fail-under=80 --api-cov-report-path=coverage.json
    - uses: actions/upload-artifact@v4
      with:
        name: api-coverage-report
        path: coverage.json
```

## Troubleshooting

### No App Found

If you see "No API app found", you have several options:

**Option 1 - Auto-discovery (Zero Config)**
Place your app in a standard location with a standard name:
- Files: `app.py`, `main.py`, `server.py`, `wsgi.py`, `asgi.py`
- Variable names: `app`, `application`, `main`, `server`

**Option 2 - Custom Location (Any File/Path)**
Create a `conftest.py` file to specify your app location:

```python
import pytest
from my_project.api.server import my_flask_app  # Any import path
# or from src.backend.main import fastapi_instance
# or from anywhere import your_app

@pytest.fixture
def app():
    return my_flask_app  # Return your app instance
```

**Option 3 - Override Auto-discovery**
If you have multiple auto-discoverable files or want to use a different app:

```python
# Even if you have app.py, you can override it
import pytest
from main import my_real_app  # Use this instead of app.py

@pytest.fixture
def app():
    return my_real_app
```

**Option 4 - Setup Wizard**
Run the interactive setup: `pytest-api-cov init`

The plugin will automatically find your app using the `app` fixture first, then fall back to auto-discovery in common locations. This means you can place your app **anywhere** as long as you create the fixture.

### Multiple App Files

If you have multiple files that could be auto-discovered (e.g., both `app.py` and `main.py`), the plugin will use the **first valid app it finds** in this priority order:

1. `app.py` 
2. `main.py`
3. `server.py`
4. `wsgi.py`
5. `asgi.py`

To use a specific app when multiple exist, create a `conftest.py` with an `app` fixture pointing to your preferred app.

### No Endpoints Discovered

If you see "No endpoints discovered":

1. Check that your app is properly instantiated
2. Verify your routes/endpoints are defined
3. Ensure the `coverage_client` fixture is working in your tests
4. Use `-v` or `-vv` for debug information

### Framework Not Detected

The plugin supports:
- **FastAPI**: Detected by `from fastapi import` or `import fastapi`
- **Flask**: Detected by `from flask import` or `import flask`

Other frameworks are not currently supported.

## License

This project is licensed under the Apache License 2.0.