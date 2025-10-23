"""init pytest_api_cov."""

try:
    from importlib.metadata import version

    __version__ = version("pytest-api-cov")
except ImportError:
    __version__ = "unknown"
