"""
Sample migration file for testing - Foreign key operations migration
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("myapp", "0006_index_constraints_migration"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaseorder",
            name="user",
            field=models.ForeignKey(
                to="myapp.user",
                on_delete=models.CASCADE,
                related_name="orders",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="referrer",
            field=models.ForeignKey(
                to="myapp.user",
                on_delete=models.SET_NULL,
                null=True,
                blank=True,
                related_name="referred_users",
            ),
        ),
        migrations.AlterField(
            model_name="purchaseorder",
            name="user",
            field=models.ForeignKey(
                to="myapp.user",
                on_delete=models.PROTECT,
                related_name="purchase_orders",
            ),
        ),
    ]
