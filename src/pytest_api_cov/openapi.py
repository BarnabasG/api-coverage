"""OpenAPI spec parsing."""

import json
import logging
from pathlib import Path
from typing import List

import yaml

logger = logging.getLogger(__name__)

HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "TRACE"}


def parse_openapi_spec(path: str) -> List[str]:
    """Parse OpenAPI spec and return list of 'METHOD /path' strings."""
    spec_path = Path(path).resolve()
    if not spec_path.exists():
        logger.error(f"OpenAPI spec not found: {spec_path}")
        return []

    try:
        with spec_path.open("r", encoding="utf-8") as f:
            spec = yaml.safe_load(f) if spec_path.suffix.lower() in (".yaml", ".yml") else json.load(f)
    except Exception:
        logger.exception("Failed to parse OpenAPI spec", exc_info=True)
        return []

    endpoints: List[str] = []
    for path_key, path_item in spec.get("paths", {}).items():
        endpoints.extend(f"{method.upper()} {path_key}" for method in path_item if method.upper() in HTTP_METHODS)

    return sorted(endpoints)
