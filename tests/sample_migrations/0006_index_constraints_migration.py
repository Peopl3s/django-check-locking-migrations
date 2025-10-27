"""
Sample migration file for testing - Index and constraint operations migration
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("myapp", "0005_rename_operations"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="user",
            index=models.Index(fields=["email"], name="idx_user_email_unique"),
        ),
        migrations.AddIndex(
            model_name="purchaseorder",
            index=models.Index(fields=["order_status", "created_at"], name="idx_order_status_date"),
        ),
        migrations.AlterUniqueTogether(
            name="user",
            unique_together={("email", "login_name")},
        ),
        migrations.AlterIndexTogether(
            name="purchaseorder",
            index_together={("order_status", "total_amount")},
        ),
    ]
