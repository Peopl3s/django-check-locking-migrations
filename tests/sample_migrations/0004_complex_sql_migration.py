"""
Sample migration file for testing - Complex SQL operations migration
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("myapp", "0003_runpython_migration"),
    ]

    operations = [
        migrations.RunSQL(
            [
                "ALTER TABLE myapp_user ADD COLUMN phone VARCHAR(20);",
                "CREATE INDEX idx_user_email ON myapp_user(email);",
                "UPDATE myapp_user SET phone = '+1234567890' WHERE phone IS NULL;",
            ],
            reverse_sql=[
                "DROP INDEX idx_user_email;",
                "ALTER TABLE myapp_user DROP COLUMN phone;",
            ],
        ),
        migrations.RunSQL(
            "ALTER TABLE myapp_order ADD COLUMN total_amount DECIMAL(10,2) DEFAULT 0.00;",
            reverse_sql="ALTER TABLE myapp_order DROP COLUMN total_amount;",
        ),
    ]
