# Django Migration Lock Checker

Pre-commit hook для проверки блокировок нескольких больших таблиц в Django миграциях.

## Установка

Добавьте в ваш `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/your-username/django-migration-lock-checker
    rev: v0.1.0
    hooks:
      - id: check-django-migration-locks
        # Опциональные аргументы:
        args: [
          "--tables", "users", "orders", "payments", "audit_logs",
          "--min-tables", "2",
          "--verbose"
        ]
