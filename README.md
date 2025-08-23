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

The plugin will automatically discover your Flask/FastAPI app if it's in common locations:
- `app.py` (with variable `app`, `application`, or `main`)
- `main.py` (with variable `app`, `application`, or `main`) 
- `server.py` (with variable `app`, `application`, or `server`)

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

@app.get("/health")
def health_check():
    return {"status": "ok"}
```

And this test file:

```python
def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200

def test_get_user(client):
    response = client.get("/users/123")
    assert response.status_code == 200
```

Running `pytest --api-cov-report` produces:

```
API Coverage Report
Uncovered Endpoints:
  [X] /health

Total API Coverage: 66.67%
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

Create a `conftest.py` file:

```python
import pytest
from your_app import app

@pytest.fixture
def app():
    return app
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

# Exclude endpoints from coverage
exclusion_patterns = [
    "/health",
    "/metrics", 
    "/docs"
]

# Save detailed JSON report
report_path = "api_coverage.json"

# Force Unicode symbols in output
force_sugar = true

# Force no Unicode symbols in output
force_sugar_disabled = true
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

# Exclude specific endpoints
pytest --api-cov-report --api-cov-exclusion-patterns="/health" --api-cov-exclusion-patterns="/docs"

# Verbose logging (shows discovery process)
pytest --api-cov-report -v

# Debug logging (very detailed)
pytest --api-cov-report -vv
```

## Framework Support

### FastAPI

Works automatically with FastAPI applications. The plugin detects FastAPI apps and uses the TestClient for coverage tracking.

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()

@app.get("/items/{item_id}")
def read_item(item_id: int):
    return {"item_id": item_id}

# Tests automatically get a 'client' fixture
def test_read_item(client):
    response = client.get("/items/42")
    assert response.status_code == 200
```

### Flask

Works automatically with Flask applications. The plugin detects Flask apps and uses the test client for coverage tracking.

```python
from flask import Flask

app = Flask(__name__)

@app.route("/users/<int:user_id>")
def get_user(user_id):
    return {"user_id": user_id}

# Tests automatically get a 'client' fixture  
def test_get_user(client):
    response = client.get("/users/123")
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

If you see "No API app found", ensure:

1. Your app is in a standard location (`app.py`, `main.py`, etc.)
2. Your app variable has a standard name (`app`, `application`, `main`)
3. Your app imports are correct (`from fastapi import FastAPI` or `from flask import Flask`)

Or use the setup wizard: `pytest-api-cov init`

### No Endpoints Discovered

If you see "No endpoints discovered":

1. Check that your app is properly instantiated
2. Verify your routes/endpoints are defined
3. Ensure the `client` fixture is working in your tests
4. Use `-v` or `-vv` for debug information

### Framework Not Detected

The plugin supports:
- **FastAPI**: Detected by `from fastapi import` or `import fastapi`
- **Flask**: Detected by `from flask import` or `import flask`

Other frameworks are not currently supported.

## License

This project is licensed under the Apache License 2.0.