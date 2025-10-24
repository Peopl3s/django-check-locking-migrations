"""
Sample migration file for testing - Critical migration (multiple large tables)
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('myapp', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='User',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='Order',
            name='status',
            field=models.CharField(max_length=50, default='pending'),
        ),
        migrations.RunSQL(
            "ALTER TABLE payments ADD COLUMN processed BOOLEAN DEFAULT FALSE;",
            reverse_sql="ALTER TABLE payments DROP COLUMN processed;"
        ),
    ]
