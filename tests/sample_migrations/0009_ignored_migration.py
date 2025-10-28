# nolock

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("myapp", "0008_data_only_migration"),
    ]

    operations = [
        migrations.AddField(
            model_name="User",
            name="is_verified",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="Order",
            name="is_processed",
            field=models.BooleanField(default=False),
        ),
        migrations.RunSQL(
            "ALTER TABLE payments ADD COLUMN verified BOOLEAN DEFAULT FALSE;",
            reverse_sql="ALTER TABLE payments DROP COLUMN verified;",
        ),
    ]
