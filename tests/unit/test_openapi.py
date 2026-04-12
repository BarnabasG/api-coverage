"""Unit tests for OpenAPI parser."""

import json

import pytest
import yaml

from pytest_api_cov.openapi import parse_openapi_spec


class TestParseOpenApiSpec:
    """Tests for parse_openapi_spec."""

    def test_parse_json_spec_success(self, tmp_path):
        """Parse a valid JSON OpenAPI spec."""
        spec_content = {
            "openapi": "3.0.0",
            "paths": {"/users": {"get": {}, "post": {}}, "/items/{itemId}": {"put": {}}},
        }
        spec_file = tmp_path / "openapi.json"
        spec_file.write_text(json.dumps(spec_content))

        endpoints = parse_openapi_spec(str(spec_file))

        assert len(endpoints) == 3
        assert "GET /users" in endpoints
        assert "POST /users" in endpoints
        assert "PUT /items/{itemId}" in endpoints

    def test_parse_yaml_spec_success(self, tmp_path):
        """Parse a valid YAML OpenAPI spec."""
        spec_content = """
        openapi: 3.0.0
        paths:
          /users:
            get: {}
            post: {}
          /items/{itemId}:
            put: {}
        """
        spec_file = tmp_path / "openapi.yaml"
        spec_file.write_text(spec_content)

        endpoints = parse_openapi_spec(str(spec_file))

        assert len(endpoints) == 3
        assert "GET /users" in endpoints
        assert "POST /users" in endpoints
        assert "PUT /items/{itemId}" in endpoints

    def test_file_not_found(self):
        """Non-existent file returns empty list."""
        endpoints = parse_openapi_spec("non_existent.json")
        assert endpoints == []

    def test_invalid_json_syntax(self, tmp_path):
        """Invalid JSON returns empty list."""
        spec_file = tmp_path / "invalid.json"
        spec_file.write_text("{invalid json")

        endpoints = parse_openapi_spec(str(spec_file))
        assert endpoints == []

    def test_invalid_yaml_syntax(self, tmp_path):
        """Invalid YAML returns empty list."""
        spec_file = tmp_path / "invalid.yaml"
        spec_file.write_text("invalid: yaml: :")

        endpoints = parse_openapi_spec(str(spec_file))
        assert endpoints == []

    def test_missing_paths_key(self, tmp_path):
        """Missing 'paths' key returns empty list."""
        spec_content = {"openapi": "3.0.0", "info": {}}
        spec_file = tmp_path / "openapi.json"
        spec_file.write_text(json.dumps(spec_content))

        endpoints = parse_openapi_spec(str(spec_file))
        assert endpoints == []

    def test_unsupported_file_extension(self, tmp_path):
        """Unsupported extension falls back to JSON parsing."""
        spec_file = tmp_path / "spec.txt"
        spec_file.write_text("{}")

        endpoints = parse_openapi_spec(str(spec_file))
        assert endpoints == []
