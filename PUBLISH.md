# Publishing Guide

This document explains how the automatic publishing workflow works and how to set it up.

## Overview

The repository uses GitHub Actions to automatically publish new versions to PyPI when code is pushed to the `master` or `main` branch. The workflow reads the version from `pyproject.toml` and creates a corresponding Git tag.

## How It Works

1. **Version Detection**: The workflow reads the version from `pyproject.toml` using `uv version` command (available in uv 0.8+).

2. **Check Existing Versions**: 
   - Checks if a Git tag `v{version}` already exists
   - Checks if the version is already published to PyPI

3. **Create Git Tag**: If the tag doesn't exist, creates and pushes a `v{version}` tag to the repository

4. **Run Tests**: Executes the full test pipeline (formatting, linting, type checking, tests)

5. **Build Package**: Builds the package using `uv build`

6. **Publish to PyPI**: Publishes to PyPI using `uv publish`

7. **Verify**: Verifies the package was published successfully

## Setup Instructions

### 1. Create PyPI API Token

1. Go to [PyPI Account Settings](https://pypi.org/manage/account/)
2. Scroll down to "API tokens"
3. Click "Add API token"
4. Create a token with a name like "GitHub Actions publish"
5. Select "Entire account" scope
6. Copy the token (you'll only see it once!)

### 2. Add GitHub Secret

**Use a Repository Secret** (not Environment Secret) for this use case.

1. Go to your GitHub repository
2. Navigate to: **Settings** → **Secrets and variables** → **Actions**
3. Click **"New repository secret"**
4. Name: `PYPI_TOKEN`
5. Value: Paste your PyPI API token
6. Click **Add secret**

### 3. Enable GitHub Actions

The workflows are automatically enabled when you push to GitHub. You can verify they exist:

- `.github/workflows/publish.yml` - Publishes to PyPI
- `.github/workflows/ci.yml` - Runs tests on PRs and pushes

## Publishing Process

### Automatic Publishing

Pushing to `master` or `main` triggers automatic publishing if:

- The version in `pyproject.toml` doesn't exist on PyPI yet
- The version tag doesn't exist in Git
- All tests pass
- The `PYPI_TOKEN` secret is configured

### Manual Publishing

You can manually trigger a publish by:

1. Going to **Actions** tab in GitHub
2. Selecting "Publish to PyPI" workflow
3. Clicking **Run workflow** button
4. Selecting the branch (master/main)
5. Clicking **Run workflow**

### Publishing a New Version

To release a new version:

1. **Update version in `pyproject.toml`**:
   ```toml
   [project]
   name = "pytest-api-cov"
   version = "1.2.0"  # ← Change this
   ```

2. **Commit and push to master**:
   ```bash
   git add pyproject.toml
   git commit -m "Bump version to 1.2.0"
   git push origin master
   ```

3. **Wait for GitHub Actions** to run automatically

## Workflow Files

### `.github/workflows/publish.yml`

Main publishing workflow triggered on pushes to master/main.

**Key features:**
- Reads version from `pyproject.toml`
- Checks if already published (skips if duplicate version)
- Creates Git tag automatically
- Runs full test pipeline
- Builds and publishes to PyPI
- Verifies publication

### `.github/workflows/ci.yml`

Continuous integration for pull requests.

**Key features:**
- Runs on multiple Python versions (3.10, 3.11, 3.12)
- Runs on multiple OS (Ubuntu, Windows, macOS)
- Checks code formatting
- Runs linting
- Runs type checking
- Runs unit and integration tests
- Warns if version already exists on PyPI

### Version Detection

The workflows use `uv version` (available in uv 0.8+) to extract the version directly from `pyproject.toml`. No additional scripts needed!

## Troubleshooting

### "PYPI_TOKEN secret is not set"

**Solution**: Add the `PYPI_TOKEN` secret in GitHub repository settings as described above.

### "Version already exists on PyPI"

**Solution**: Bump the version in `pyproject.toml` and try again.

### "Tests failing"

**Solution**: Fix the failing tests. The workflow won't publish if tests fail.

### "Git tag already exists"

**Solution**: The workflow will skip creating the tag if it already exists. This is safe to ignore.

## Manual Publishing (Without GitHub Actions)

If you need to publish manually:

```bash
# Run the full pipeline
make pipeline

# Build the package
make build

# Set your PyPI token
export PYPI_TOKEN="your-token-here"
echo $PYPI_TOKEN > .pypi_token

# Publish
make publish
```

## Publishing to Test PyPI

To publish to Test PyPI instead:

```bash
# Set your Test PyPI token
echo $TEST_PYPI_TOKEN > .test_pypi_token

# Publish to Test PyPI
make publish-test
```

Or create a separate workflow by copying `.github/workflows/publish.yml` and modifying it to use `TEST_PYPI_TOKEN` and the `--index testpypi` flag.
