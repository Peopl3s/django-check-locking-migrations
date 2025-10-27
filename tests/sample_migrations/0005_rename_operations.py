"""
Sample migration file for testing - Rename operations migration
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("myapp", "0004_complex_sql_migration"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="Order",
            new_name="PurchaseOrder",
        ),
        migrations.RenameField(
            model_name="User",
            old_name="username",
            new_name="login_name",
        ),
        migrations.RenameField(
            model_name="PurchaseOrder",
            old_name="status",
            new_name="order_status",
        ),
    ]
