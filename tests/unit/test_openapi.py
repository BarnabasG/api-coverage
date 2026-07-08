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

    def test_empty_yaml_spec(self, tmp_path):
        """An empty YAML file parses to None and must not crash fixture setup."""
        spec_file = tmp_path / "empty.yaml"
        spec_file.write_text("")

        assert parse_openapi_spec(str(spec_file)) == []

    def test_non_mapping_spec(self, tmp_path):
        """A top-level list is not a valid spec and must not crash."""
        spec_file = tmp_path / "list.json"
        spec_file.write_text("[1, 2, 3]")

        assert parse_openapi_spec(str(spec_file)) == []

    def test_non_mapping_paths_section(self, tmp_path):
        """A non-mapping paths section returns no endpoints."""
        spec_file = tmp_path / "badpaths.json"
        spec_file.write_text(json.dumps({"openapi": "3.0.0", "paths": ["not", "a", "mapping"]}))

        assert parse_openapi_spec(str(spec_file)) == []

    def test_non_mapping_path_item_is_skipped(self, tmp_path):
        """Malformed path items are skipped, valid ones kept."""
        spec_file = tmp_path / "baditem.json"
        spec_file.write_text(json.dumps({"paths": {"/users": {"get": {}}, "/bad": "nope"}}))

        assert parse_openapi_spec(str(spec_file)) == ["GET /users"]
