"""
Sample migration file for testing - Data-only operations migration (safe)
"""

from django.db import migrations


def populate_default_data(apps, schema_editor):
    """Populate default data"""
    User = apps.get_model('myapp', 'User')
    PurchaseOrder = apps.get_model('myapp', 'PurchaseOrder')
    
    # Create some default users
    User.objects.create(
        login_name='admin',
        email='admin@example.com',
        is_active=True
    )
    
    # Update existing orders with default values
    PurchaseOrder.objects.filter(total_amount=0).update(total_amount=99.99)


def reverse_populate_default_data(apps, schema_editor):
    """Reverse data population"""
    User = apps.get_model('myapp', 'User')
    PurchaseOrder = apps.get_model('myapp', 'PurchaseOrder')
    
    # Remove default users
    User.objects.filter(login_name='admin').delete()
    
    # Reset order amounts
    PurchaseOrder.objects.filter(total_amount=99.99).update(total_amount=0)


class Migration(migrations.Migration):
    dependencies = [
        ("myapp", "0007_foreign_key_migration"),
    ]

    operations = [
        migrations.RunPython(
            populate_default_data,
            reverse_populate_default_data,
            elidable=True,  # This migration can be squashed
        ),
        migrations.RunSQL(
            "UPDATE myapp_user SET is_active = TRUE WHERE is_active IS NULL;",
            reverse_sql="UPDATE myapp_user SET is_active = NULL WHERE is_active = TRUE;",
        ),
    ]
