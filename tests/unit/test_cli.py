"""Unit tests for pytest-api-cov CLI module."""

import os
import tempfile
from unittest.mock import Mock, patch, mock_open
import pytest

from pytest_api_cov.cli import (
    detect_framework_and_app,
    generate_conftest_content,
    generate_pyproject_config,
    cmd_init,
    main,
)


class TestDetectFrameworkAndApp:
    """Tests for detect_framework_and_app function."""

    def test_no_files_exist(self):
        """Test detection when no app files exist."""
        with patch('os.path.exists', return_value=False):
            result = detect_framework_and_app()
            assert result is None

    @pytest.mark.parametrize("framework,import_stmt,var_name,expected_file,expected_var", [
        ("FastAPI", "from fastapi import FastAPI", "app", "app.py", "app"),
        ("Flask", "from flask import Flask", "application", "app.py", "application"),
        ("FastAPI", "import fastapi\nfrom fastapi import FastAPI", "main", "main.py", "main"),
    ])
    def test_framework_app_detection(self, framework, import_stmt, var_name, expected_file, expected_var):
        """Test detection of various framework apps."""
        if framework == "FastAPI":
            app_content = f"""
{import_stmt}

{var_name} = FastAPI()

@{var_name}.get("/")
def root():
    return {{"message": "hello"}}
"""
        else:  # Flask
            app_content = f"""
{import_stmt}

{var_name} = Flask(__name__)

@{var_name}.route("/")
def root():
    return "hello"
"""
        
        def mock_exists(path):
            return path == expected_file
        
        with patch('os.path.exists', side_effect=mock_exists), \
             patch('builtins.open', mock_open(read_data=app_content)):
            result = detect_framework_and_app()
            assert result == (framework, expected_file, expected_var)

    def test_no_framework_detected(self):
        """Test when file exists but no framework imports found."""
        app_content = """
import sys

def hello():
    return "hello"
"""
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=app_content)):
            result = detect_framework_and_app()
            assert result is None

    def test_framework_but_no_app_variable(self):
        """Test when framework is imported but no app variable found."""
        app_content = """
from fastapi import FastAPI

# No app variable defined
"""
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=app_content)):
            result = detect_framework_and_app()
            assert result is None

    def test_file_read_exception(self):
        """Test handling of file read exceptions."""
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', side_effect=IOError("Cannot read file")):
            result = detect_framework_and_app()
            assert result is None

    def test_multiple_files_checked(self):
        """Test that multiple files are checked in order."""
        flask_content = """
from flask import Flask
server = Flask(__name__)
"""
        
        def mock_exists(path):
            return path in ["app.py", "server.py"]
        
        def mock_open_handler(path, mode='r'):
            if path == "app.py":
                # First file has no framework
                return mock_open(read_data="# just a comment")()
            elif path == "server.py":
                # Second file has Flask
                return mock_open(read_data=flask_content)()
        
        with patch('os.path.exists', side_effect=mock_exists), \
             patch('builtins.open', side_effect=mock_open_handler):
            result = detect_framework_and_app()
            assert result == ("Flask", "server.py", "server")


class TestGenerateConftestContent:
    """Tests for generate_conftest_content function."""

    def test_fastapi_conftest(self):
        """Test generating conftest for FastAPI."""
        content = generate_conftest_content("FastAPI", "app.py", "app")
        
        assert "import pytest" in content
        assert "from app import app" in content
        assert "def app():" in content
        assert "Provide the FastAPI app" in content
        assert "return app" in content

    def test_flask_conftest(self):
        """Test generating conftest for Flask."""
        content = generate_conftest_content("Flask", "main.py", "application")
        
        assert "import pytest" in content
        assert "from main import application" in content
        assert "def app():" in content
        assert "Provide the Flask app" in content
        assert "return application" in content


class TestGeneratePyprojectConfig:
    """Tests for generate_pyproject_config function."""

    def test_pyproject_config_structure(self):
        """Test structure of generated pyproject config."""
        config = generate_pyproject_config("FastAPI")
        
        assert "[tool.pytest_api_cov]" in config
        assert "show_uncovered_endpoints = true" in config
        assert "show_covered_endpoints = false" in config
        assert "show_excluded_endpoints = false" in config
        assert "# fail_under = 80.0" in config
        assert "# exclusion_patterns" in config
        assert "# report_path" in config
        assert "# force_sugar" in config


class TestCmdInit:
    """Tests for cmd_init function."""

    @patch('pytest_api_cov.cli.detect_framework_and_app')
    @patch('builtins.input')
    @patch('pytest_api_cov.cli.os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    @patch('builtins.print')
    def test_init_success_no_existing_files(self, mock_print, mock_file, mock_exists, mock_input, mock_detect):
        """Test successful init with no existing files."""
        mock_detect.return_value = ("FastAPI", "app.py", "app")
        mock_exists.return_value = False  # No existing files
        mock_input.return_value = "y"  # User agrees to create pyproject.toml
        
        result = cmd_init()
        
        assert result == 0
        # Should create both conftest.py and pyproject.toml
        assert mock_file.call_count == 2
        mock_print.assert_any_call("✅ Created conftest.py")
        mock_print.assert_any_call("✅ Created pyproject.toml")

    @patch('pytest_api_cov.cli.detect_framework_and_app')
    @patch('builtins.input')
    @patch('pytest_api_cov.cli.os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    @patch('builtins.print')
    def test_init_with_existing_conftest(self, mock_print, mock_file, mock_exists, mock_input, mock_detect):
        """Test init with existing conftest.py."""
        mock_detect.return_value = ("Flask", "app.py", "app")
        
        def exists_side_effect(path):
            return path == "conftest.py"
        
        mock_exists.side_effect = exists_side_effect
        mock_input.side_effect = ["y", "n"]  # Overwrite conftest, don't create pyproject
        
        result = cmd_init()
        
        assert result == 0
        mock_print.assert_any_call("⚠️  conftest.py already exists")
        mock_print.assert_any_call("✅ Created conftest.py")

    @patch('pytest_api_cov.cli.detect_framework_and_app')
    @patch('builtins.input')
    @patch('pytest_api_cov.cli.os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    @patch('builtins.print')
    def test_init_with_existing_pyproject(self, mock_print, mock_file, mock_exists, mock_input, mock_detect):
        """Test init with existing pyproject.toml."""
        mock_detect.return_value = ("FastAPI", "main.py", "main")
        
        def exists_side_effect(path):
            return path == "pyproject.toml"
        
        mock_exists.side_effect = exists_side_effect
        
        result = cmd_init()
        
        assert result == 0
        mock_print.assert_any_call("ℹ️  pyproject.toml already exists")
        mock_print.assert_any_call("Add this configuration to your pyproject.toml:")

    @patch('pytest_api_cov.cli.detect_framework_and_app')
    @patch('builtins.input')
    @patch('pytest_api_cov.cli.os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    @patch('builtins.print')
    def test_init_user_declines_conftest_overwrite(self, mock_print, mock_file, mock_exists, mock_input, mock_detect):
        """Test when user declines to overwrite existing conftest."""
        mock_detect.return_value = ("FastAPI", "app.py", "app")
        mock_exists.return_value = True  # conftest.py exists
        mock_input.side_effect = ["n", "n"]  # Don't overwrite conftest, don't create pyproject
        
        result = cmd_init()
        
        assert result == 0
        mock_print.assert_any_call("⚠️  conftest.py already exists")
        # Should not see "Created conftest.py" message

    @patch('pytest_api_cov.cli.detect_framework_and_app')
    @patch('builtins.open', new_callable=mock_open)
    @patch('builtins.print')
    def test_init_no_app_detected(self, mock_print, mock_file, mock_detect):
        """Test init when no app is detected."""
        mock_detect.return_value = None
        
        result = cmd_init()
        
        assert result == 1
        mock_print.assert_any_call("❌ No FastAPI or Flask app detected in common locations")
        mock_print.assert_any_call("Example app.py:")

    @patch('pytest_api_cov.cli.detect_framework_and_app')
    @patch('builtins.print')
    def test_init_prints_next_steps(self, mock_print, mock_detect):
        """Test that init prints helpful next steps."""
        mock_detect.return_value = ("FastAPI", "app.py", "app")
        
        with patch('pytest_api_cov.cli.os.path.exists', return_value=False), \
             patch('builtins.input', return_value="n"), \
             patch('builtins.open', mock_open()):
            result = cmd_init()
        
        assert result == 0
        mock_print.assert_any_call("🎉 Setup complete!")
        mock_print.assert_any_call("Next steps:")
        mock_print.assert_any_call("1. Write your tests using the 'client' fixture")
        mock_print.assert_any_call("2. Run: pytest --api-cov-report")


class TestMain:
    """Tests for main function."""

    @patch('pytest_api_cov.cli.cmd_init')
    @patch('sys.argv', ['pytest-api-cov', 'init'])
    def test_main_init_command(self, mock_cmd_init):
        """Test main with init command."""
        mock_cmd_init.return_value = 0
        
        result = main()
        
        assert result == 0
        mock_cmd_init.assert_called_once()

    @patch('builtins.print')
    @patch('sys.argv', ['pytest-api-cov'])
    def test_main_no_command(self, mock_print):
        """Test main with no command (should show help)."""
        result = main()
        
        assert result == 1
        # Help should be printed (we can't easily test the exact content)

    @patch('builtins.print')
    @patch('sys.argv', ['pytest-api-cov', 'unknown'])
    def test_main_unknown_command(self, mock_print):
        """Test main with unknown command."""
        with pytest.raises(SystemExit) as exc_info:
            main()
        
        # argparse exits with code 2 for invalid arguments
        assert exc_info.value.code == 2

    @patch('pytest_api_cov.cli.cmd_init')
    @patch('sys.argv', ['pytest-api-cov', 'init'])
    def test_main_init_command_failure(self, mock_cmd_init):
        """Test main when init command fails."""
        mock_cmd_init.return_value = 1
        
        result = main()
        
        assert result == 1
