"""Unit tests for OpenAPI parser."""

import json
import pytest
import yaml
from unittest.mock import patch, mock_open
from pytest_api_cov.openapi import parse_openapi_spec


class TestParseOpenApiSpec:
    """Tests for parse_openapi_spec function."""

    def test_parse_json_spec_success(self, tmp_path):
        """Test parsing a valid JSON OpenAPI spec."""
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
        """Test parsing a valid YAML OpenAPI spec."""
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
        """Test handling of non-existent file."""
        endpoints = parse_openapi_spec("non_existent.json")
        assert endpoints == []

    def test_invalid_json_syntax(self, tmp_path):
        """Test handling of invalid JSON syntax."""
        spec_file = tmp_path / "invalid.json"
        spec_file.write_text("{invalid json")

        endpoints = parse_openapi_spec(str(spec_file))
        assert endpoints == []

    def test_invalid_yaml_syntax(self, tmp_path):
        """Test handling of invalid YAML syntax."""
        spec_file = tmp_path / "invalid.yaml"
        spec_file.write_text("invalid: yaml: :")

        endpoints = parse_openapi_spec(str(spec_file))
        assert endpoints == []

    def test_missing_paths_key(self, tmp_path):
        """Test handling of spec without 'paths' key."""
        spec_content = {"openapi": "3.0.0", "info": {}}
        spec_file = tmp_path / "openapi.json"
        spec_file.write_text(json.dumps(spec_content))

        endpoints = parse_openapi_spec(str(spec_file))
        assert endpoints == []

    def test_unsupported_file_extension(self, tmp_path):
        """Test handling of unsupported file extension."""
        spec_file = tmp_path / "spec.txt"
        spec_file.write_text("{}")

        # Should probably log an error or return empty, depending on implementation.
        # Assuming current implementation tries to parse based on extension or content.
        # Let's check the implementation if needed, but for now expect empty or handled.
        endpoints = parse_openapi_spec(str(spec_file))
        assert endpoints == []
