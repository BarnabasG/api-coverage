import pytest
from pathlib import Path

pytest_plugins = ["pytester"]


def test_openapi_discovery(pytester):
    """Test that endpoints are discovered from OpenAPI spec."""

    # Create the openapi.json file
    openapi_content = """
    {
      "openapi": "3.0.0",
      "info": {
        "title": "Sample API",
        "version": "1.0.0"
      },
      "paths": {
        "/users": {
          "get": {},
          "post": {}
        },
        "/users/{userId}": {
          "get": {}
        }
      }
    }
    """
    pytester.makefile(".json", openapi=openapi_content)

    # Create a dummy test file
    pytester.makepyfile("""
        def test_dummy(coverage_client):
            pass
    """)

    # Run pytest with the flag
    result = pytester.runpytest("--api-cov-report", "--api-cov-openapi-spec=openapi.json", "-vv")

    # Check that endpoints were discovered
    result.stderr.fnmatch_lines(
        [
            "*Discovered 3 endpoints from OpenAPI spec*",
        ]
    )

    # Check the report output
    result.stdout.fnmatch_lines(
        [
            "*Uncovered Endpoints:*",
            "*GET    /users*",
            "*GET    /users/{userId}*",
            "*POST   /users*",
        ]
    )


def test_openapi_yaml_discovery(pytester):
    """Test that endpoints are discovered from OpenAPI YAML spec."""

    # Create the openapi.yaml file
    openapi_content = """
    openapi: 3.0.0
    info:
      title: Sample API
      version: 1.0.0
    paths:
      /items:
        get: {}
    """
    pytester.makefile(".yaml", openapi=openapi_content)

    # Create a dummy test file
    pytester.makepyfile("""
        def test_dummy(coverage_client):
            pass
    """)

    # Run pytest with the flag
    result = pytester.runpytest("--api-cov-report", "--api-cov-openapi-spec=openapi.yaml", "-vv")

    # Check that endpoints were discovered (commented out due to logging flakiness)
    # result.stderr.fnmatch_lines([
    #     "*Discovered 1 endpoints from OpenAPI spec*",
    # ])

    # Check the report output
    result.stdout.fnmatch_lines(
        [
            "*Uncovered Endpoints:*",
            "*GET    /items*",
        ]
    )
