# Django Migration Lock Checker

Pre-commit hook для проверки блокировок нескольких больших таблиц в Django миграциях.

## Установка

Добавьте в ваш `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/Peopl3s/django-check-locking-migrations
    rev: v0.2.0  # используйте последнюю версию
    hooks:
      - id: check-django-migration-locks
        name: 🚫 BLOCK migrations locking multiple big tables
        args: [
          "--tables", "flat", "project",
          "--min-tables", "2",  # ⚠️ Блокировать при 2+ таблицах
          "--verbose",
          "--strict"  # ⚠️ Обязательно блокировать коммит
        ]
