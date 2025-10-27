# Contributing to Django Migration Lock Checker

Thank you for your interest in contributing to Django Migration Lock Checker! This document provides guidelines and information to help you get started with contributing to this project.

## 🎯 Project Overview

Django Migration Lock Checker is a pre-commit hook that prevents dangerous database migrations from locking multiple large tables simultaneously. It analyzes Django migration files and blocks commits if they contain operations that could cause production downtime or performance issues.

## 🚀 Getting Started

### Prerequisites

- Python 3.6 or higher
- Git
- Basic knowledge of Django migrations
- Familiarity with pre-commit hooks (helpful but not required)

### Development Environment Setup

1. **Fork and Clone the Repository**
   ```bash
   # Fork the repository on GitHub, then clone your fork
   git clone https://github.com/YOUR_USERNAME/django-check-locking-migrations.git
   cd django-check-locking-migrations
   
   # Add the original repository as upstream
   git remote add upstream https://github.com/Peopl3s/django-check-locking-migrations.git
   ```

2. **Create a Virtual Environment**
   ```bash
   # Using venv (recommended)
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   
   # Or using conda
   conda create -n django-migration-lock-checker python=3.9
   conda activate django-migration-lock-checker
   ```

3. **Install Development Dependencies**
   ```bash
   # Install with development dependencies
   pip install .[dev]
   
   # Or using the Makefile
   make install-dev
   ```

4. **Verify Installation**
   ```bash
   # Run tests to ensure everything is working
   make test
   
   # Check that the CLI tool is available
   check-migration-locks --help
   ```

## 🧪 Testing

### Running Tests

We use pytest for testing. The project includes comprehensive tests covering various migration scenarios.

```bash
# Run all tests
make test
# or
pytest tests/

# Run tests with verbose output
make test-verbose
# or
pytest tests/ -v

# Run tests with coverage report
make test-coverage
# or
pytest tests/ --cov=migration_lock_checker --cov-report=html --cov-report=term

# Run specific test file
pytest tests/test_migration_lock_checker.py -v

# Run tests by marker
pytest tests/ -m unit  # Unit tests only
pytest tests/ -m integration  # Integration tests only
pytest tests/ -m edge_case  # Edge case tests only
```

### Test Structure

- `tests/test_migration_lock_checker.py` - Main test suite
- `tests/sample_migrations/` - Sample migration files for testing
- `tests/test_config.json` - Test configuration file

### Writing Tests

When adding new features or fixing bugs, please include appropriate tests:

1. **Unit Tests**: Test individual functions and methods
2. **Integration Tests**: Test the complete workflow
3. **Edge Case Tests**: Test boundary conditions and error scenarios

Example test structure:
```python
import pytest
from migration_lock_checker.check_migration_locks import MigrationLockChecker

class TestNewFeature:
    def test_basic_functionality(self):
        """Test basic functionality of the new feature"""
        pass
    
    def test_edge_case(self):
        """Test edge cases"""
        pass
    
    @pytest.mark.integration
    def test_integration(self):
        """Test integration with existing functionality"""
        pass
```

## 📝 Code Style and Quality

We use ruff for linting and formatting, and mypy for type checking.

### Code Formatting

```bash
# Format code
make format
# or
ruff format migration_lock_checker/ tests/

# Check formatting without making changes
ruff format --check migration_lock_checker/ tests/
```

### Linting

```bash
# Run linting
make lint
# or
ruff check migration_lock_checker/ tests/

# Fix auto-fixable issues
ruff check --fix migration_lock_checker/ tests/
```

### Type Checking

```bash
# Run type checking
make type-check
# or
mypy migration_lock_checker/
```

### Code Style Guidelines

- **Line Length**: 88 characters (following Black/ruff standards)
- **Quotes**: Use double quotes for strings
- **Imports**: Use isort-style import organization (handled by ruff)
- **Type Hints**: Include type hints for all public functions and methods
- **Documentation**: Include docstrings for all public functions and classes

## 🏗️ Project Structure

```
django-check-locking-migrations/
├── migration_lock_checker/           # Main package
│   ├── __init__.py
│   └── check_migration_locks.py     # Core functionality
├── tests/                           # Test suite
│   ├── __init__.py
│   ├── test_migration_lock_checker.py
│   ├── test_config.json
│   ├── run_tests.py
│   └── sample_migrations/           # Test migration files
│       ├── __init__.py
│       ├── 0001_initial.py
│       ├── 0002_critical_migration.py
│       └── ...
├── .pre-commit-hooks.yaml           # Pre-commit hook configuration
├── CONTRIBUTING.md                  # This file
├── LICENSE                          # MIT License
├── Makefile                         # Development commands
├── README.md                        # Project documentation
├── pyproject.toml                   # Project configuration
├── pytest.ini                       # pytest configuration
└── setup.py                         # Package setup
```

## 🔄 Development Workflow

### 1. Create a Feature Branch

```bash
# Sync with upstream
git fetch upstream
git checkout main
git merge upstream/main

# Create a new branch
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bug-fix
```

### 2. Make Your Changes

- Write clean, well-documented code
- Follow the existing code style
- Add tests for new functionality
- Update documentation if needed

### 3. Test Your Changes

```bash
# Run all tests
make test

# Run linting and formatting
make lint
make format

# Run type checking
make type-check

# Run the full test suite with coverage
make test-coverage
```

### 4. Commit Your Changes

We follow [Conventional Commits](https://www.conventionalcommits.org/) specification:

```bash
# Format: <type>(<scope>): <description>

# Features
git commit -m "feat(parser): add support for new migration operation"

# Bug fixes
git commit -m "fix(cli): handle empty migration list correctly"

# Documentation
git commit -m "docs(readme): update installation instructions"

# Tests
git commit -m "test(migrations): add tests for complex SQL operations"

# Refactoring
git commit -m "refactor(core): simplify table detection logic"
```

### 5. Push and Create Pull Request

```bash
# Push to your fork
git push origin feature/your-feature-name

# Create a Pull Request on GitHub
# Include:
# - Clear description of changes
# - Related issues (if any)
# - Testing instructions
# - Screenshots (if applicable)
```

## 📋 Pull Request Guidelines

### Before Submitting

1. **Tests**: Ensure all tests pass
2. **Code Quality**: Run linting and formatting
3. **Documentation**: Update relevant documentation
4. **Changelog**: Add entry to CHANGELOG.md (if applicable)

### Pull Request Template

```markdown
## Description
Brief description of changes made.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] All tests pass
- [ ] New tests added for new functionality
- [ ] Manual testing completed

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No breaking changes (or clearly documented)
```

### Review Process

1. **Automated Checks**: CI will run tests and code quality checks
2. **Code Review**: Maintainers will review your changes
3. **Feedback**: Address any feedback or requested changes
4. **Merge**: Once approved, your PR will be merged

## 🐛 Bug Reports

When reporting bugs, please include:

1. **Environment**: Python version, Django version, OS
2. **Steps to Reproduce**: Clear steps to reproduce the issue
3. **Expected Behavior**: What you expected to happen
4. **Actual Behavior**: What actually happened
5. **Sample Code**: Minimal example demonstrating the issue
6. **Error Messages**: Full error traceback (if applicable)

## 💡 Feature Requests

For feature requests:

1. **Use Case**: Describe the problem you're trying to solve
2. **Proposed Solution**: How you envision the feature working
3. **Alternatives**: Any alternative solutions you've considered
4. **Additional Context**: Any other relevant information

## 📚 Documentation

### Types of Documentation

1. **Code Documentation**: Docstrings and comments
2. **README.md**: Project overview and quick start
3. **CONTRIBUTING.md**: Development guidelines (this file)
4. **API Documentation**: Detailed API reference (if needed)

### Documentation Guidelines

- Use clear, concise language
- Include code examples
- Keep documentation up-to-date with code changes
- Use consistent formatting

## 🏷️ Release Process

Releases are managed by project maintainers:

1. **Version Bumping**: Follow semantic versioning
2. **Changelog**: Update CHANGELOG.md
3. **Tagging**: Create Git tag
4. **PyPI**: Publish to Python Package Index

## 🤝 Community Guidelines

### Code of Conduct

- Be respectful and inclusive
- Welcome newcomers and help them learn
- Focus on constructive feedback
- Assume good intentions

### Getting Help

- **GitHub Issues**: For bug reports and feature requests
- **GitHub Discussions**: For questions and general discussion
- **Documentation**: Check existing documentation first

## 🛠️ Useful Commands

```bash
# Development setup
make install-dev    # Install with dev dependencies
make clean         # Clean temporary files

# Testing
make test          # Run tests
make test-verbose  # Verbose tests
make test-coverage # Tests with coverage

# Code quality
make lint          # Run linting
make format        # Format code
make type-check    # Type checking

# Other
make help          # Show all available commands
```

## 📞 Contact

- **Maintainer**: Peopl3s
- **Repository**: https://github.com/Peopl3s/django-check-locking-migrations
- **Issues**: https://github.com/Peopl3s/django-check-locking-migrations/issues
- **Discussions**: https://github.com/Peopl3s/django-check-locking-migrations/discussions

---

Thank you for contributing to Django Migration Lock Checker! Your contributions help make Django migrations safer for everyone. 🚀
