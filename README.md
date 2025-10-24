# Django Migration Lock Checker

🚫 **Pre-commit hook that blocks commits when Django migrations lock multiple large tables simultaneously**

[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)
[![Python](https://img.shields.io/badge/python-3.6+-blue.svg)](https://python.org)
[![Django](https://img.shields.io/badge/django-2.2+-green.svg)](https://djangoproject.com)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## 🎯 Purpose

This tool prevents dangerous database migrations that could lock multiple large tables simultaneously, potentially causing production downtime or performance issues. It analyzes Django migration files and blocks commits if they contain operations that lock too many critical tables.

## ✨ Features

- **🔍 Comprehensive Analysis**: Detects all Django migration operations (CreateModel, AddField, RunSQL, etc.)
- **⚡ Real-time Blocking**: Pre-commit hook that stops dangerous commits before they happen
- **🎛️ Configurable**: Define which tables are "large" and set your risk tolerance
- **📊 Detailed Reporting**: Clear output showing which tables are locked and why
- **🛠️ Easy Integration**: Simple setup with pre-commit or manual usage
- **🧪 Well Tested**: Comprehensive test suite with 29+ tests using pytest

## 🚀 Quick Start

### Installation

```bash
# Install the package
pip install django-migration-lock-checker

# Or install from source
git clone https://github.com/Peopl3s/django-check-locking-migrations.git
cd django-check-locking-migrations
pip install .
```

### Pre-commit Setup

Add to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/Peopl3s/django-check-locking-migrations
    rev: v0.2.0  # use the latest version
    hooks:
      - id: check-django-migration-locks
        name: 🚫 BLOCK migrations locking multiple big tables
        args: [
          "--tables", "users", "orders", "payments", "audit_logs",
          "--min-tables", "2",  # ⚠️ Block on 2+ tables
          "--verbose",
          "--strict"  # ⚠️ Always block commit
        ]
```

### Manual Usage

```bash
# Check specific migration files
check-migration-locks app/migrations/0001_add_fields.py

# Check with custom table list
check-migration-locks --tables users orders payments app/migrations/*.py

# Verbose output
check-migration-locks --verbose --min-tables 3 app/migrations/*.py
```

## 📋 Configuration

### Command Line Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--tables` | `-t` | List of large tables to monitor | `users,orders,payments,audit_logs,logs` |
| `--min-tables` | `-m` | Minimum locked tables to block commit | `2` |
| `--app` | `-a` | Django app name for table prefixing | `None` |
| `--verbose` | `-v` | Enable detailed output | `False` |
| `--strict` | `-s` | Strict mode (always block on issues) | `True` |
| `--config` | `-c` | JSON configuration file | `None` |

### Configuration File

Create a `migration-lock-config.json`:

```json
{
  "tables": ["users", "orders", "payments", "audit_logs"],
  "min_tables": 2,
  "app": "myapp",
  "verbose": true,
  "strict": true
}
```

Use it with:
```bash
check-migration-locks --config migration-lock-config.json app/migrations/*.py
```

## 🔍 What It Detects

### Django Migration Operations
- `CreateModel` - Table creation
- `AddField` - Column addition (ALTER TABLE)
- `RemoveField` - Column removal (ALTER TABLE)
- `AlterField` - Column modification (ALTER TABLE)
- `RenameField` - Column renaming (ALTER TABLE RENAME COLUMN)
- `RunSQL` - Custom SQL operations
- `RunPython` - Python code execution

### SQL Operations
- `ALTER TABLE` - Table modifications
- `RENAME COLUMN` - Column renaming operations
- `CREATE INDEX` - Index creation
- `DROP INDEX` - Index removal
- `TRUNCATE TABLE` - Table truncation
- `DROP TABLE` - Table deletion
- `UPDATE without WHERE` - Dangerous bulk updates
- `DELETE without WHERE` - Dangerous bulk deletions

## 📊 Example Output

### Safe Migration (Allowed)
```
🔍 Pre-commit: checking 1 migrations for large table locks
📊 Monitoring tables: users, orders, payments
🚫 COMMIT BLOCKED at: 2+ locked tables
------------------------------------------------------------
✅ OK app/migrations/0001_add_email.py - locked tables: 1
------------------------------------------------------------
✅ All migrations passed check! Commit allowed.
```

### Dangerous Migration (Blocked)
```
🔍 Pre-commit: checking 1 migrations for large table locks
📊 Monitoring tables: users, orders, payments
🚫 COMMIT BLOCKED at: 2+ locked tables
------------------------------------------------------------
❌ app/migrations/0002_critical_migration.py
   🚨 BLOCKED 2 LARGE TABLES: users, orders
------------------------------------------------------------
🚫 COMMIT BLOCKED!
🚨 Critical migrations found (1):

   📁 app/migrations/0002_critical_migration.py
   📊 Locked tables: 2
   🗂️  Tables: users, orders

💡 HOW TO FIX:
   1. Split migration into multiple parts
   2. Use `Atomic = False` in migration class
   3. Execute operations sequentially in different migrations
   4. For urgent fixes use: git commit --no-verify

🔒 Commit BLOCKED due to DB lock risk!
```

## 🛠️ Development

### Running Tests

```bash
# Using pytest (recommended)
pytest tests/ -v

# Using the test runner
python tests/run_tests.py

# Using Makefile
make test          # Run tests
make test-verbose  # Run tests with verbose output
make test-coverage # Run tests with coverage report
```

### Installing for Development

```bash
# Clone the repository
git clone https://github.com/Peopl3s/django-check-locking-migrations.git
cd django-check-locking-migrations

# Install with development dependencies (includes ruff for linting/formatting)
pip install .[dev]

# Install with test dependencies only
pip install .[test]
```

### Code Quality

```bash
# Run linting (replaces flake8)
make lint

# Format code (replaces black)
make format

# Or use ruff directly
ruff check migration_lock_checker/ tests/
ruff format migration_lock_checker/ tests/
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes and add tests
4. Run tests: `make test`
5. Commit your changes: `git commit -m 'Add amazing feature'`
6. Push to the branch: `git push origin feature/amazing-feature`
7. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🔗 Related Projects

- [Django](https://djangoproject.com/) - The web framework for perfectionists with deadlines
- [pre-commit](https://pre-commit.com/) - A framework for managing and maintaining multi-language pre-commit hooks
- [pytest](https://pytest.org/) - A mature full-featured Python testing tool

## 📞 Support

- 🐛 **Bug Reports**: Open an issue on GitHub
- 💡 **Feature Requests**: Open an issue with the "enhancement" label
- 📧 **Questions**: Use GitHub Discussions
- 📖 **Documentation**: See `tests/README.md` for detailed test documentation

---

**⚠️ Important**: This tool is designed to prevent production issues. Always test migrations in a staging environment before deploying to production.
