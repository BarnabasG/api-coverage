# pytest-api-cov

A **pytest plugin** that measures **API endpoint coverage** for FastAPI and Flask applications. Know which endpoints are tested and which are missing coverage.

## Features

- **Zero Configuration**: Plug-and-play with Flask/FastAPI apps - just install and run
- **Client-Based Discovery**: Automatically extracts app from your existing test client fixtures
- **Terminal Reports**: Rich terminal output with detailed coverage information
- **JSON Reports**: Export coverage data for CI/CD integration

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

Discovery in this plugin is client-based: the plugin extracts the application instance from your test client fixtures, or from an `app` fixture when present. This means the plugin integrates with the test clients or fixtures you already use in your tests rather than relying on background file scanning.

How discovery works (in order):

1. If you configure one or more candidate client fixture names (see configuration below), the plugin will try each in order and wrap the first matching fixture it finds.
2. If no configured client fixture is found, the plugin will look for a standard `app` fixture and use that to create a tracked client.
3. If neither a client fixture nor an `app` fixture is available (or the plugin cannot extract an app from the client), coverage tracking will be skipped and a helpful message is shown.

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

Total API Coverage: 75.0%
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

### See examples

```bash
# Print an example pyproject.toml configuration snippet
pytest-api-cov show-pyproject

# Print an example conftest.py for a known app module
pytest-api-cov show-conftest FastAPI src.main app
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

The plugin can wrap existing test client fixtures automatically. Recent changes allow you to specify one or more candidate fixture names (the plugin will try them in order) instead of a single configured name.

Default client fixture names the plugin will look for (in order):
- `client`
- `test_client`
- `api_client`
- `app_client`

If you use a different fixture name, you can provide one or more names via the CLI flag `--api-cov-client-fixture-names` (repeatable) or in `pyproject.toml` under `[tool.pytest_api_cov]` as `client_fixture_names` (a list).


#### Option 1: Configuration-Based (recommended for most users)

Configure one or more existing fixture names to be discovered and wrapped automatically by the plugin.

Example `pyproject.toml`:

```toml
[tool.pytest_api_cov]
# Provide a list of candidate fixture names the plugin should try (order matters)
client_fixture_names = ["my_custom_client"]
```

Or use the CLI flag multiple times:

```bash
pytest --api-cov-report --api-cov-client-fixture-names=my_custom_client --api-cov-client-fixture-names=another_fixture
```

If the configured fixture(s) are not found, the plugin will try to use an `app` fixture (if present) to create a tracked client. If neither is available or the plugin cannot extract the app from a discovered client fixture, the tests will still run — coverage will simply be unavailable and a warning will be logged.

#### Option 2: Helper Function

Use the `create_coverage_fixture` helper to create a custom fixture name:

```python
# conftest.py
import pytest
from pytest_api_cov.plugin import create_coverage_fixture

# Create a new fixture with custom name
my_client = create_coverage_fixture('my_client')

# Or wrap an existing fixture
@pytest.fixture
def original_flask_client():
    from flask.testing import FlaskClient
    from your_app import app
    return app.test_client()

flask_client = create_coverage_fixture('flask_client', 'original_flask_client')

def test_endpoint(my_client):
    response = my_client.get("/endpoint")
    assert response.status_code == 200

def test_with_flask_client(flask_client):
    response = flask_client.get("/endpoint")
    assert response.status_code == 200
```

The helper returns a pytest fixture you can assign to a name in `conftest.py`.


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
# Optionally prefix a pattern with one or more HTTP methods to target only those methods,
exclusion_patterns = [
    "/health",
    "/metrics",
    "/docs/*",
    "/admin/*",
    "!/admin/public",
    "GET,POST /users/*"
]

# Save detailed JSON report
report_path = "api_coverage.json"

# Force Unicode symbols in output
force_sugar = true

# Force no Unicode symbols in output
force_sugar_disabled = true

# Provide candidate fixture names (in priority order).
client_fixture_names = ["my_custom_client"]

# Group HTTP methods by endpoint for legacy behavior (default: false)
group_methods_by_endpoint = false

```
Notes on exclusion patterns

- Method prefixes (optional): If a pattern starts with one or more HTTP method names followed by whitespace, the pattern applies only to those methods. Methods may be comma-separated and are matched case-insensitively. Example: `GET,POST /users/*`.
- Path-only patterns (default): If no method is specified the pattern applies to all methods for the matching path (existing behaviour).
- Wildcards: Use `*` to match any characters in the path portion (not a regex; dots and other characters are treated literally unless `*` is used).
- Negation: Prefix a pattern with `!` to override earlier exclusions and re-include a path (or method-specific path). Negations can also include method prefixes (e.g. `!GET /admin/health`).
- Matching: Patterns are tested against both the full `METHOD /path` string and the `/path` portion to remain compatible with existing configurations.

Examples (pyproject or CLI):

- Exclude the `/health` path for all methods:

```toml
exclusion_patterns = ["/health"]
```

- Exclude only GET requests to `/health`:

```toml
exclusion_patterns = ["GET /health"]
```

- Exclude GET and POST for `/users/*` but re-include GET /users/42:

```toml
exclusion_patterns = ["GET,POST /users/*", "!GET /users/42"]
```

Or using the CLI flags (repeatable):

```bash
pytest --api-cov-report --api-cov-exclusion-patterns="GET,POST /users/*" --api-cov-exclusion-patterns="!GET /users/42"
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

# Specify one or more existing client fixture names (repeatable)
pytest --api-cov-report --api-cov-client-fixture-names=my_custom_client --api-cov-client-fixture-names=another_fixture

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

If coverage is not running because the plugin could not locate an app, check the following:

- Ensure you are running pytest with `--api-cov-report` enabled.
- Confirm you have a test client fixture (e.g. `client`, `test_client`, `api_client`) or an `app` fixture in your test suite.
- If you use a custom client fixture, add its name to `client_fixture_names` in `pyproject.toml` or pass it via the CLI using `--api-cov-client-fixture-names` (repeatable) so the plugin can find and wrap it.
- If the plugin finds the client fixture but cannot extract the underlying app (for example the client type is not supported or wrapped in an unexpected way), you will see a message like "Could not extract app from client" — in that case either provide an `app` fixture directly or wrap your existing client using `create_coverage_fixture`.

### No endpoints Discovered

If you still see no endpoints discovered:

1. Check that your app is properly instantiated inside the fixture or client.
2. Verify your routes/endpoints are defined and reachable by the test client.
3. Ensure the `coverage_client` fixture is being used in your tests (or that your configured client fixture is listed and discovered).
4. Use `-v` or `-vv` for debug logging to see why the plugin skipped discovery or wrapping.

### Framework Not Detected

The plugin supports:
- **FastAPI**: Detected by `FastAPI` class
- **Flask**: Detected by `Flask` class
- **FlaskOpenAPI3**: Detected by `FlaskOpenAPI3` class

Other frameworks are not currently supported.

## License

This project is licensed under the Apache License 2.0.
