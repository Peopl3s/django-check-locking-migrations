# Django Migration Lock Checker

Pre-commit hook for checking locks on multiple large tables in Django migrations.

## Installation

Add to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/Peopl3s/django-check-locking-migrations
    rev: v0.2.0  # use the latest version
    hooks:
      - id: check-django-migration-locks
        name: 🚫 BLOCK migrations locking multiple big tables
        args: [
          "--tables", "flat", "project",
          "--min-tables", "2",  # ⚠️ Block on 2+ tables
          "--verbose",
          "--strict"  # ⚠️ Always block commit
        ]
