"""
Sample migration file for testing - RunPython migration (data migration)
"""

from django.db import migrations


def update_user_emails(apps, schema_editor):
    """Forward function for data migration"""
    User = apps.get_model('myapp', 'User')
    User.objects.filter(email__isnull=True).update(email='default@example.com')


def reverse_update_user_emails(apps, schema_editor):
    """Reverse function for data migration"""
    User = apps.get_model('myapp', 'User')
    User.objects.filter(email='default@example.com').update(email=None)


class Migration(migrations.Migration):
    dependencies = [
        ("myapp", "0002_critical_migration"),
    ]

    operations = [
        migrations.RunPython(
            update_user_emails,
            reverse_update_user_emails,
        ),
    ]
